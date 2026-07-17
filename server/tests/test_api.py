import logging
import os
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://workflow_studio:workflow_studio_dev_password@127.0.0.1:5432/workflow_studio_test",
)
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("RUN_JOB_QUEUE_BACKEND", "thread")

from fastapi.testclient import TestClient

from server.src.auth import AuthService, set_auth_service
from server.src import main as api
from server.src import runner
from server.src import workflow_router
from server.src.orm import Base, DbSession, DbWorkspaceInvitation
from server.src.providers import aliyun
from server.src.db import create_session_factory
from server.src.jobs import RunJobQueue, RunJobWorker
from server.src.knowledge import set_knowledge_session_factory
from server.src.models import RunResponse, RunStep, WorkflowPayload
from server.src.storage import WorkflowStore


def valid_workflow() -> dict:
    return {
        "name": "API Unit Test Workflow",
        "version": "0.2.0",
        "nodes": [
            {
                "id": "input-1",
                "position": {"x": 0, "y": 0},
                "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
            },
            {
                "id": "output-1",
                "position": {"x": 260, "y": 0},
                "data": {"kind": "output", "label": "最终回答", "prompt": "{{user_request}}", "outputKey": "answer"},
            },
        ],
        "edges": [{"id": "e1", "source": "input-1", "target": "output-1"}],
    }


def invalid_workflow() -> dict:
    workflow = valid_workflow()
    workflow["nodes"] = [workflow["nodes"][1]]
    workflow["edges"] = []
    return workflow


def named_workflow(name: str) -> dict:
    workflow = valid_workflow()
    workflow["name"] = name
    return workflow


class NullCache:
    def get_json(self, key: str):
        return None

    def set_json(self, key: str, value, ttl_seconds: int) -> None:
        return None


class MemoryCache(NullCache):
    def __init__(self) -> None:
        self.values = {}
        self.read_count = 0
        self.write_count = 0

    def get_json(self, key: str):
        self.read_count += 1
        return self.values.get(key)

    def set_json(self, key: str, value, ttl_seconds: int) -> None:
        self.write_count += 1
        self.values[key] = value


class FailingCache(NullCache):
    def get_json(self, key: str):
        raise RuntimeError("cache unavailable")

    def set_json(self, key: str, value, ttl_seconds: int) -> None:
        raise RuntimeError("cache unavailable")


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls) -> None:
        logging.disable(logging.NOTSET)

    def setUp(self) -> None:
        self.previous_store = api.store
        self.previous_auth_service = api.auth_service
        self.previous_cache = api.cache
        engine, session_factory = create_session_factory(TEST_DATABASE_URL)
        self.engine = engine
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.previous_search_paismart = runner.search_paismart
        api.store = WorkflowStore(session_factory=session_factory, engine=engine)
        set_knowledge_session_factory(api.store.SessionLocal)
        api.job_queue = RunJobQueue(api.store, backend="thread")
        api.auth_service = AuthService(api.store)
        set_auth_service(api.auth_service)
        api.cache = NullCache()
        self.client = TestClient(api.app)
        self.auth_headers = self.create_auth_headers()

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        api.store = self.previous_store
        set_knowledge_session_factory(api.store.SessionLocal)
        api.job_queue = RunJobQueue(api.store, backend="thread")
        api.auth_service = self.previous_auth_service
        set_auth_service(self.previous_auth_service)
        api.cache = self.previous_cache
        runner.search_paismart = self.previous_search_paismart

    def create_auth_headers(self, username: str | None = None) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username or f"user-{uuid4().hex[:8]}", "password": "password123"},
        )
        self.assertEqual(response.status_code, 201)
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def test_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "postgresql")
        self.assertEqual(body["queue_backend"], "thread")

    def test_workflow_router_matches_smart_building_workflow(self) -> None:
        building = self.client.post(
            "/api/workflows",
            json=named_workflow("智能楼宇设备异常诊断与运维派单"),
            headers=self.auth_headers,
        ).json()
        self.client.post(
            "/api/workflows",
            json=named_workflow("短视频口播与配图生成"),
            headers=self.auth_headers,
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/workflow-router/match",
                json={"input_text": "A座楼宇设备 AHU-18F-07 离线告警，请诊断并派工单"},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workflow_id"], building["id"])
        self.assertGreaterEqual(body["confidence"], 0.68)
        self.assertFalse(body["needs_confirmation"])
        self.assertIn("规则路由", body["provider"])

    def test_workflow_router_uses_configured_llm_decision(self) -> None:
        building = self.client.post(
            "/api/workflows",
            json=named_workflow("智能楼宇设备异常诊断与运维派单"),
            headers=self.auth_headers,
        ).json()
        self.client.post(
            "/api/workflows",
            json=named_workflow("短视频口播与配图生成"),
            headers=self.auth_headers,
        )
        model_output = (
            '{"workflow_id":"'
            + building["id"]
            + '","reason":"设备离线问题应交给楼宇运维流程","confidence":0.93}'
        )

        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-router-key", "OPENAI_API_KEY": ""}),
            patch.object(workflow_router, "run_deepseek_node", return_value=(model_output, "deepseek-test")),
        ):
            response = self.client.post(
                "/api/workflow-router/match",
                json={"input_text": "设备离线了，请帮我处理"},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workflow_id"], building["id"])
        self.assertEqual(body["provider"], "DeepSeek - deepseek-test")
        self.assertEqual(body["confidence"], 0.93)
        self.assertFalse(body["needs_confirmation"])

    def test_workflow_router_runs_high_confidence_match(self) -> None:
        building = self.client.post(
            "/api/workflows",
            json=named_workflow("智能楼宇设备异常诊断与运维派单"),
            headers=self.auth_headers,
        ).json()
        self.client.post(
            "/api/workflows",
            json=named_workflow("短视频口播与配图生成"),
            headers=self.auth_headers,
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/workflow-router/runs",
                json={"input_text": "楼宇新风设备离线，请查询告警并生成运维工单"},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["route"]["workflow_id"], building["id"])
        self.assertIsNotNone(body["run"])
        self.assertEqual(body["run"]["workflow_id"], building["id"])
        self.assertEqual(body["run"]["status"], "ok")

    def test_workflow_router_requires_confirmation_for_ambiguous_input(self) -> None:
        self.client.post(
            "/api/workflows",
            json=named_workflow("智能楼宇设备异常诊断与运维派单"),
            headers=self.auth_headers,
        )
        self.client.post(
            "/api/workflows",
            json=named_workflow("短视频口播与配图生成"),
            headers=self.auth_headers,
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/workflow-router/runs",
                json={"input_text": "帮我处理一下这个问题"},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["route"]["needs_confirmation"])
        self.assertIsNone(body["run"])
        self.assertGreaterEqual(len(body["route"]["candidates"]), 2)

    def test_customer_chat_runs_workflow_without_exposing_internal_route(self) -> None:
        self.client.post(
            "/api/workflows",
            json=named_workflow("客户问题处理"),
            headers=self.auth_headers,
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/customer-chat/messages",
                json={"message": "请帮我处理这个问题", "history": []},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertTrue(body["reply"])
        self.assertTrue(body["run_id"])
        self.assertNotIn("route", body)
        self.assertNotIn("workflow_name", body)
        self.assertNotIn("workflow_id", body)

    def test_customer_chat_asks_for_clarification_without_exposing_candidates(self) -> None:
        self.client.post(
            "/api/workflows",
            json=named_workflow("智能楼宇设备异常诊断与运维派单"),
            headers=self.auth_headers,
        )
        self.client.post(
            "/api/workflows",
            json=named_workflow("短视频口播与配图生成"),
            headers=self.auth_headers,
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/customer-chat/messages",
                json={"message": "帮我处理一下", "history": []},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertIsNone(body["run_id"])
        self.assertNotIn("candidates", body)
        self.assertNotIn("route", body)

    def test_customer_chat_uses_recent_conversation_for_routing(self) -> None:
        building = self.client.post(
            "/api/workflows",
            json=named_workflow("智能楼宇设备异常诊断与运维派单"),
            headers=self.auth_headers,
        ).json()
        self.client.post(
            "/api/workflows",
            json=named_workflow("短视频口播与配图生成"),
            headers=self.auth_headers,
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/customer-chat/messages",
                json={
                    "message": "AHU-18F-07 现在离线告警了",
                    "history": [
                        {"role": "user", "content": "A座智能楼宇里的新风设备"},
                        {"role": "assistant", "content": "请描述具体情况"},
                    ],
                },
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        run = self.client.get(f"/api/runs/{body['run_id']}", headers=self.auth_headers).json()
        self.assertEqual(run["workflow_id"], building["id"])

    def test_customer_chat_accepts_long_previous_assistant_reply(self) -> None:
        self.client.post(
            "/api/workflows",
            json=named_workflow("短视频口播与配图生成"),
            headers=self.auth_headers,
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/customer-chat/messages",
                json={
                    "message": "再生成一版，更温暖一点",
                    "history": [
                        {"role": "user", "content": "帮我生成短视频素材"},
                        {"role": "assistant", "content": "上一轮输出：" + "很长的结果" * 1200},
                    ],
                },
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["status"], {"completed", "needs_clarification", "error"})

    def test_customer_chat_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/customer-chat/messages",
            json={"message": "你好", "history": []},
        )
        self.assertEqual(response.status_code, 401)

    def test_customer_workspace_role_can_chat_but_cannot_read_internal_workflows(self) -> None:
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        owner_workspace_headers = {**self.auth_headers, "X-Workspace-Id": workspace["id"]}
        self.client.post("/api/workflows", json=valid_workflow(), headers=owner_workspace_headers)
        invitation = self.client.post(
            f"/api/workspaces/{workspace['id']}/invitations",
            json={"role": "customer"},
            headers=self.auth_headers,
        ).json()
        customer_headers = self.create_auth_headers()
        accepted = self.client.post(
            "/api/workspaces/invitations/accept",
            json={"code": invitation["code"]},
            headers=customer_headers,
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["role"], "customer")

        customer_workspace_headers = {**customer_headers, "X-Workspace-Id": workspace["id"]}
        workspace_records = self.client.get("/api/workspaces", headers=customer_headers).json()
        joined = next(record for record in workspace_records if record["id"] == workspace["id"])
        self.assertEqual(joined["role"], "customer")

        self.assertEqual(
            self.client.get("/api/workflows", headers=customer_workspace_headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/runs", headers=customer_workspace_headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/audit-logs", headers=customer_workspace_headers).status_code,
            403,
        )
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            chat = self.client.post(
                "/api/customer-chat/messages",
                json={"message": "请帮我处理这个问题", "history": []},
                headers=customer_workspace_headers,
            )
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["status"], "completed")

    def test_mock_building_bms_mcp_tool(self) -> None:
        response = self.client.post(
            "/mcp/building-bms/get-device-status",
            json={"device_id": "AHU-18F-07", "building": "A座", "floor": "18F"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tool"], "mcp.building_bms.get_device_status")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["device_id"], "AHU-18F-07")
        self.assertEqual(body["data"]["connection_status"], "offline")

    def test_mcp_tool_list_and_named_call(self) -> None:
        list_response = self.client.get("/mcp/tools")
        self.assertEqual(list_response.status_code, 200)
        tool_names = [tool["name"] for tool in list_response.json()["tools"]]
        self.assertIn("mcp.building_bms.get_device_status", tool_names)

        call_response = self.client.post(
            "/mcp/tools/mcp/building_bms/get_device_status/call",
            json={"device_id": "AHU-18F-07", "building": "A座", "floor": "18F"},
        )
        self.assertEqual(call_response.status_code, 200)
        body = call_response.json()
        self.assertEqual(body["tool"], "mcp.building_bms.get_device_status")
        self.assertEqual(body["data"]["alarm_level"], "P1")

    def test_container_api_fallback_url_rewrites_localhost_tool_url(self) -> None:
        rewritten = runner.container_api_fallback_url("http://127.0.0.1:8000/mcp/building-bms/get-device-status")
        self.assertEqual(rewritten, "http://api:8000/mcp/building-bms/get-device-status")
        self.assertIsNone(runner.container_api_fallback_url("http://127.0.0.1:5173/mcp/building-bms/get-device-status"))

    def test_admin_overview_reports_workspace_status(self) -> None:
        response = self.client.get("/api/admin/overview", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "postgresql")
        self.assertEqual(body["queue_backend"], "thread")
        self.assertEqual(body["workspace"]["role"], "owner")
        self.assertGreaterEqual(body["counts"]["members"], 1)
        self.assertEqual(body["settings"]["session_ttl_hours"], 168)
        self.assertEqual(body["settings"]["workspace_invitation_ttl_hours"], 168)
        self.assertIn("provider_status", body)
        self.assertIn("knowledge_status", body)
        self.assertIn("run_metrics", body)
        self.assertEqual(body["run_metrics"]["total_runs"], 0)
        self.assertIn("recent_audit_logs", body)

    def test_admin_overview_uses_short_lived_cache(self) -> None:
        cache = MemoryCache()
        api.cache = cache

        first_response = self.client.get("/api/admin/overview", headers=self.auth_headers)
        self.assertEqual(first_response.status_code, 200)
        first_body = first_response.json()

        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        api.store.create_run(None, user["id"], "缓存后新增运行", "ok", RunResponse(status="ok", steps=[]), workspace["id"])

        second_response = self.client.get("/api/admin/overview", headers=self.auth_headers)

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["run_metrics"]["total_runs"], first_body["run_metrics"]["total_runs"])
        self.assertEqual(cache.read_count, 2)
        self.assertEqual(cache.write_count, 1)

    def test_admin_overview_falls_back_when_cache_fails(self) -> None:
        api.cache = FailingCache()

        response = self.client.get("/api/admin/overview", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_admin_overview_reports_run_metrics(self) -> None:
        ok_response = RunResponse(
            status="ok",
            steps=[
                RunStep(
                    node_id="ok-1",
                    title="成功节点",
                    status="done",
                    input="input",
                    output="output",
                    kind="llm",
                    provider="DeepSeek",
                    duration_ms=40,
                )
            ],
        )
        error_response = RunResponse(
            status="error",
            steps=[
                RunStep(
                    node_id="error-1",
                    title="失败节点",
                    status="error",
                    input="input",
                    output="output",
                    kind="tool",
                    provider="HTTP 工具",
                    error="boom",
                    duration_ms=80,
                    attempt_count=2,
                )
            ],
        )
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        api.store.create_run(None, user["id"], "成功工作流", "ok", ok_response, workspace["id"])
        api.store.create_run(None, user["id"], "失败工作流", "error", error_response, workspace["id"])

        response = self.client.get("/api/admin/overview", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        metrics = response.json()["run_metrics"]
        self.assertEqual(metrics["total_runs"], 2)
        self.assertEqual(metrics["sampled_runs"], 2)
        self.assertEqual(metrics["ok_runs"], 1)
        self.assertEqual(metrics["error_runs"], 1)
        self.assertEqual(metrics["success_rate"], 50)
        self.assertEqual(metrics["average_duration_ms"], 60)
        self.assertEqual(metrics["average_step_count"], 1)
        self.assertEqual(metrics["billable_step_count"], 2)
        self.assertEqual(metrics["total_cost_units"], 14)
        self.assertEqual(metrics["average_cost_units"], 7)
        self.assertEqual(metrics["provider_breakdown"]["DeepSeek"], 10)
        self.assertEqual(metrics["provider_breakdown"]["HTTP 工具"], 4)
        self.assertEqual(metrics["recent_failed_runs"][0]["workflow_name"], "失败工作流")
        self.assertEqual(metrics["recent_failed_runs"][0]["steps"][0]["error"], "boom")
        self.assertEqual(metrics["recent_failed_runs"][0]["cost_summary"]["cost_units"], 4)

    def test_evaluation_dataset_runs_keyword_checks(self) -> None:
        workflow_response = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers)
        self.assertEqual(workflow_response.status_code, 201)
        workflow_id = workflow_response.json()["id"]
        dataset_response = self.client.post(
            "/api/evaluations/datasets",
            headers=self.auth_headers,
            json={
                "name": "客服回复评测",
                "description": "检查输出是否包含关键词。",
                "cases": [
                    {
                        "input_text": "退款多久到账？",
                        "expected_output": "应该回答退款问题。",
                        "expected_keywords": ["退款"],
                    },
                    {
                        "input_text": "普通咨询",
                        "expected_output": "故意设置一个不会命中的关键词。",
                        "expected_keywords": ["不存在的关键词"],
                    },
                ],
            },
        )
        self.assertEqual(dataset_response.status_code, 201)
        dataset = dataset_response.json()
        self.assertEqual(dataset["case_count"], 2)
        detail_response = self.client.get(f"/api/evaluations/datasets/{dataset['id']}", headers=self.auth_headers)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(len(detail_response.json()["cases"]), 2)

        run_response = self.client.post(
            f"/api/evaluations/datasets/{dataset['id']}/runs",
            headers=self.auth_headers,
            json={"workflow_id": workflow_id},
        )

        self.assertEqual(run_response.status_code, 201)
        body = run_response.json()
        self.assertEqual(body["total_cases"], 2)
        self.assertEqual(body["passed_cases"], 1)
        self.assertEqual(body["failed_cases"], 1)
        self.assertEqual(body["pass_rate"], 50)
        self.assertTrue(body["results"][0]["passed"])
        self.assertFalse(body["results"][1]["passed"])
        self.assertEqual(body["results"][1]["missing_keywords"], ["不存在的关键词"])

        history_response = self.client.get(f"/api/evaluations/runs?dataset_id={dataset['id']}", headers=self.auth_headers)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json()[0]["id"], body["id"])

    def test_auth_token_expires_and_is_pruned(self) -> None:
        register_response = self.client.post(
            "/api/auth/register",
            json={"username": f"expiring-{uuid4().hex[:8]}", "password": "password123"},
        )
        self.assertEqual(register_response.status_code, 201)
        token = register_response.json()["token"]

        with api.store._connect() as session:
            db_session = session.get(DbSession, token)
            self.assertIsNotNone(db_session)
            db_session.expires_at = "2000-01-01T00:00:00+00:00"
            session.commit()

        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 401)

        with api.store._connect() as session:
            self.assertIsNone(session.get(DbSession, token))

    def test_rejects_invalid_workflow(self) -> None:
        response = self.client.post("/api/workflows", json=invalid_workflow(), headers=self.auth_headers)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["detail"]["valid"])

    def test_run_steps_include_observability_fields(self) -> None:
        workflow = {
            **valid_workflow(),
            "nodes": [
                {
                    "id": "input-1",
                    "position": {"x": 0, "y": 0},
                    "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                },
                {
                    "id": "tool-1",
                    "position": {"x": 240, "y": 0},
                    "data": {
                        "kind": "tool",
                        "label": "失败工具",
                        "toolName": "local.unreachable",
                        "toolUrl": "http://127.0.0.1:65535/not-found",
                        "toolMethod": "GET",
                        "toolHeaders": "{}",
                        "toolParams": "{}",
                        "retryCount": 2,
                        "failurePolicy": "continue",
                        "outputKey": "tool_result",
                    },
                },
                {
                    "id": "output-1",
                    "position": {"x": 480, "y": 0},
                    "data": {"kind": "output", "label": "最终输出", "prompt": "{{tool_result}}", "outputKey": "answer"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "input-1", "target": "tool-1"},
                {"id": "e2", "source": "tool-1", "target": "output-1"},
            ],
        }

        response = self.client.post(
            "/api/runs",
            json={"workflow": workflow, "input_text": "观测字段"},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        steps = response.json()["steps"]
        self.assertGreaterEqual(steps[0]["duration_ms"], 0)
        self.assertEqual(steps[0]["attempt_count"], 1)
        self.assertEqual(steps[1]["status"], "error")
        self.assertEqual(steps[1]["kind"], "tool")
        self.assertEqual(steps[1]["attempt_count"], 3)
        self.assertGreaterEqual(steps[1]["duration_ms"], 0)

    def test_mcp_tool_node_result_feeds_json_node(self) -> None:
        workflow = {
            **valid_workflow(),
            "nodes": [
                {
                    "id": "input-1",
                    "position": {"x": 0, "y": 0},
                    "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                },
                {
                    "id": "mcp-1",
                    "position": {"x": 240, "y": 0},
                    "data": {
                        "kind": "tool",
                        "label": "MCP 查询",
                        "toolName": "mcp.building_bms.get_device_status",
                        "toolUrl": "",
                        "toolMethod": "POST",
                        "toolHeaders": "{}",
                        "toolParams": '{"device_id":"AHU-18F-07","building":"A座","floor":"18F"}',
                        "outputKey": "mcp_result",
                    },
                },
                {
                    "id": "json-1",
                    "position": {"x": 480, "y": 0},
                    "data": {
                        "kind": "json",
                        "label": "读取状态",
                        "jsonSource": "{{mcp_result}}",
                        "jsonPath": "data.connection_status",
                        "outputKey": "connection_status",
                    },
                },
                {
                    "id": "output-1",
                    "position": {"x": 720, "y": 0},
                    "data": {
                        "kind": "output",
                        "label": "最终输出",
                        "prompt": "{{connection_status}}",
                        "outputKey": "answer",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "input-1", "target": "mcp-1"},
                {"id": "e2", "source": "mcp-1", "target": "json-1"},
                {"id": "e3", "source": "json-1", "target": "output-1"},
            ],
        }

        response = self.client.post(
            "/api/runs",
            json={"workflow": workflow, "input_text": "查询楼宇设备"},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        steps = response.json()["steps"]
        self.assertEqual(steps[1]["status"], "done")
        self.assertEqual(steps[1]["provider"], "MCP 工具")
        self.assertIn('"tool": "mcp.building_bms.get_device_status"', steps[1]["output"])
        self.assertEqual(steps[2]["output"], "offline")
        self.assertEqual(steps[3]["output"], "offline")

    def test_mcp_tool_node_tolerates_unescaped_llm_context_in_params(self) -> None:
        output, step_input, error = runner.run_mcp_tool_node(
            {
                "toolName": "mcp.building_bms.get_device_status",
                "toolParams": (
                    '{\n'
                    '  "device_id": "AHU-18F-07",\n'
                    '  "building": "A-Zone",\n'
                    '  "floor": "18F",\n'
                    '  "source": "{{device_query}}"\n'
                    '}'
                ),
            },
            {
                "device_query": (
                    "Intent result:\n"
                    '- query params: {"device_id":"AHU-18F-07","building":"A-Zone","floor":"18F"}'
                )
            },
        )

        self.assertIsNone(error)
        self.assertIn('"tool": "mcp.building_bms.get_device_status"', output)
        self.assertIn('"device_id": "AHU-18F-07"', output)
        self.assertIn('"source"', step_input)

    def test_workflow_crud_persists_archive_state(self) -> None:
        create_response = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers)
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertFalse(created["archived"])

        payload = {**valid_workflow(), "archived": True}
        update_response = self.client.put(f"/api/workflows/{created['id']}", json=payload, headers=self.auth_headers)
        self.assertEqual(update_response.status_code, 200)
        self.assertTrue(update_response.json()["archived"])

        fetch_response = self.client.get(f"/api/workflows/{created['id']}", headers=self.auth_headers)
        self.assertEqual(fetch_response.status_code, 200)
        self.assertTrue(fetch_response.json()["archived"])

    def test_workflow_versions_restore_and_audit_logs(self) -> None:
        create_response = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers)
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()

        updated_payload = {**valid_workflow(), "name": "Changed Workflow"}
        update_response = self.client.put(
            f"/api/workflows/{created['id']}",
            json=updated_payload,
            headers=self.auth_headers,
        )
        self.assertEqual(update_response.status_code, 200)

        manual_version = self.client.post(
            f"/api/workflows/{created['id']}/versions",
            json={"note": "面试演示版本"},
            headers=self.auth_headers,
        )
        self.assertEqual(manual_version.status_code, 201)
        self.assertEqual(manual_version.json()["note"], "面试演示版本")

        versions = self.client.get(f"/api/workflows/{created['id']}/versions", headers=self.auth_headers)
        self.assertEqual(versions.status_code, 200)
        self.assertGreaterEqual(len(versions.json()), 3)
        oldest_version = versions.json()[-1]
        self.assertEqual(oldest_version["sequence"], 1)
        self.assertEqual(oldest_version["name"], valid_workflow()["name"])

        restore = self.client.post(
            f"/api/workflows/{created['id']}/versions/{oldest_version['id']}/restore",
            headers=self.auth_headers,
        )
        self.assertEqual(restore.status_code, 200)
        self.assertEqual(restore.json()["name"], valid_workflow()["name"])

        logs = self.client.get(
            f"/api/audit-logs?resource_type=workflow&resource_id={created['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(logs.status_code, 200)
        actions = [item["action"] for item in logs.json()]
        self.assertIn("workflow.create", actions)
        self.assertIn("workflow.update", actions)
        self.assertIn("workflow.version_restore", actions)

    def test_workflow_publish_creates_published_version_and_audit_log(self) -> None:
        create_response = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers)
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["publish_status"], "draft")
        self.assertIsNone(created["published_version_id"])

        publish_response = self.client.post(
            f"/api/workflows/{created['id']}/publish",
            json={"note": "面试演示发布版"},
            headers=self.auth_headers,
        )
        self.assertEqual(publish_response.status_code, 200)
        published = publish_response.json()
        self.assertEqual(published["publish_status"], "published")
        self.assertIsNotNone(published["published_version_id"])
        self.assertIsNotNone(published["published_at"])

        versions = self.client.get(f"/api/workflows/{created['id']}/versions", headers=self.auth_headers).json()
        published_versions = [version for version in versions if version["is_published"]]
        self.assertEqual(len(published_versions), 1)
        self.assertEqual(published_versions[0]["id"], published["published_version_id"])
        self.assertEqual(published_versions[0]["note"], "面试演示发布版")

        update_response = self.client.put(
            f"/api/workflows/{created['id']}",
            json={**valid_workflow(), "name": "Changed After Publish"},
            headers=self.auth_headers,
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["publish_status"], "changed")

        logs = self.client.get(
            f"/api/audit-logs?resource_type=workflow&resource_id={created['id']}",
            headers=self.auth_headers,
        ).json()
        self.assertIn("workflow.publish", [item["action"] for item in logs])

    def test_workflow_version_diff_reports_changed_nodes(self) -> None:
        create_response = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers)
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()

        changed = valid_workflow()
        changed["nodes"][1]["data"]["prompt"] = "新的回答模板：{{user_request}}"
        update_response = self.client.put(
            f"/api/workflows/{created['id']}",
            json=changed,
            headers=self.auth_headers,
        )
        self.assertEqual(update_response.status_code, 200)

        versions = self.client.get(f"/api/workflows/{created['id']}/versions", headers=self.auth_headers).json()
        oldest = versions[-1]
        newest = versions[0]
        diff_response = self.client.get(
            f"/api/workflows/{created['id']}/versions/diff"
            f"?base_version_id={oldest['id']}&target_version_id={newest['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(diff_response.status_code, 200)
        diff = diff_response.json()
        self.assertEqual(diff["base_version"]["id"], oldest["id"])
        self.assertEqual(diff["target_version"]["id"], newest["id"])
        self.assertEqual(diff["summary"]["changed"], 1)
        self.assertEqual(diff["changes"][0]["category"], "node")
        self.assertIn("新的回答模板", diff["changes"][0]["after"])

    def test_deleting_workflow_deletes_runs(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        run_response = self.client.post(
            f"/api/workflows/{created['id']}/runs",
            json={"input_text": "单元测试"},
            headers=self.auth_headers,
        )
        self.assertEqual(run_response.status_code, 201)

        runs_before_delete = self.client.get(f"/api/runs?workflow_id={created['id']}", headers=self.auth_headers).json()
        self.assertEqual(len(runs_before_delete), 1)

        delete_response = self.client.delete(f"/api/workflows/{created['id']}", headers=self.auth_headers)
        self.assertEqual(delete_response.status_code, 204)

        self.assertEqual(self.client.get(f"/api/workflows/{created['id']}", headers=self.auth_headers).status_code, 404)
        runs_after_delete = self.client.get(f"/api/runs?workflow_id={created['id']}", headers=self.auth_headers).json()
        self.assertEqual(runs_after_delete, [])

    def test_users_cannot_access_each_other_workflows(self) -> None:
        other_headers = self.create_auth_headers()
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()

        self.assertEqual(self.client.get(f"/api/workflows/{created['id']}", headers=other_headers).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/workflows/{created['id']}", headers=other_headers).status_code, 404)
        self.assertEqual(self.client.get(f"/api/workflows/{created['id']}", headers=self.auth_headers).status_code, 200)

    def test_workspace_membership_roles_and_isolation(self) -> None:
        viewer_headers = self.create_auth_headers("viewer-user")
        viewer_me = self.client.get("/api/auth/me", headers=viewer_headers).json()
        workspace = self.client.post(
            "/api/workspaces",
            json={"name": "共享测试空间"},
            headers=self.auth_headers,
        ).json()
        created = self.client.post(
            "/api/workflows",
            json=valid_workflow(),
            headers={**self.auth_headers, "X-Workspace-Id": workspace["id"]},
        ).json()

        denied = self.client.get(
            f"/api/workflows/{created['id']}",
            headers={**viewer_headers, "X-Workspace-Id": workspace["id"]},
        )
        self.assertEqual(denied.status_code, 403)

        member = self.client.post(
            f"/api/workspaces/{workspace['id']}/members",
            json={"username": viewer_me["username"], "role": "viewer"},
            headers=self.auth_headers,
        )
        self.assertEqual(member.status_code, 200)

        fetch = self.client.get(
            f"/api/workflows/{created['id']}",
            headers={**viewer_headers, "X-Workspace-Id": workspace["id"]},
        )
        self.assertEqual(fetch.status_code, 200)
        update = self.client.put(
            f"/api/workflows/{created['id']}",
            json=valid_workflow(),
            headers={**viewer_headers, "X-Workspace-Id": workspace["id"]},
        )
        self.assertEqual(update.status_code, 403)

        remove = self.client.delete(
            f"/api/workspaces/{workspace['id']}/members/{viewer_me['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(remove.status_code, 200)
        denied_after_remove = self.client.get(
            f"/api/workflows/{created['id']}",
            headers={**viewer_headers, "X-Workspace-Id": workspace["id"]},
        )
        self.assertEqual(denied_after_remove.status_code, 403)

        owner_me = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        remove_self = self.client.delete(
            f"/api/workspaces/{workspace['id']}/members/{owner_me['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(remove_self.status_code, 404)

    def test_workspace_invitation_accept_and_revoke(self) -> None:
        invited_headers = self.create_auth_headers("invited-user")
        blocked_headers = self.create_auth_headers("blocked-user")
        workspace = self.client.post(
            "/api/workspaces",
            json={"name": "邀请测试空间"},
            headers=self.auth_headers,
        ).json()
        create_invitation = self.client.post(
            f"/api/workspaces/{workspace['id']}/invitations",
            json={"role": "editor"},
            headers=self.auth_headers,
        )
        self.assertEqual(create_invitation.status_code, 201)
        invitation = create_invitation.json()
        self.assertEqual(invitation["status"], "pending")
        self.assertEqual(invitation["role"], "editor")

        accepted = self.client.post(
            "/api/workspaces/invitations/accept",
            json={"code": invitation["code"]},
            headers=invited_headers,
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "accepted")

        members = self.client.get(f"/api/workspaces/{workspace['id']}/members", headers=self.auth_headers).json()
        invited_member = next(member for member in members if member["username"] == "invited-user")
        self.assertEqual(invited_member["role"], "editor")

        revoked_invitation = self.client.post(
            f"/api/workspaces/{workspace['id']}/invitations",
            json={"role": "viewer"},
            headers=self.auth_headers,
        ).json()
        revoke = self.client.delete(
            f"/api/workspaces/{workspace['id']}/invitations/{revoked_invitation['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(revoke.status_code, 200)
        self.assertEqual(revoke.json()["status"], "revoked")

        rejected = self.client.post(
            "/api/workspaces/invitations/accept",
            json={"code": revoked_invitation["code"]},
            headers=blocked_headers,
        )
        self.assertEqual(rejected.status_code, 404)

    def test_expired_workspace_invitation_cannot_be_accepted(self) -> None:
        invited_headers = self.create_auth_headers("expired-invite-user")
        workspace = self.client.post(
            "/api/workspaces",
            json={"name": "过期邀请空间"},
            headers=self.auth_headers,
        ).json()
        invitation = self.client.post(
            f"/api/workspaces/{workspace['id']}/invitations",
            json={"role": "viewer"},
            headers=self.auth_headers,
        ).json()

        with api.store._connect() as session:
            db_invitation = session.get(DbWorkspaceInvitation, invitation["id"])
            self.assertIsNotNone(db_invitation)
            db_invitation.expires_at = "2000-01-01T00:00:00+00:00"
            session.commit()

        rejected = self.client.post(
            "/api/workspaces/invitations/accept",
            json={"code": invitation["code"]},
            headers=invited_headers,
        )
        self.assertEqual(rejected.status_code, 404)

        invitations = self.client.get(
            f"/api/workspaces/{workspace['id']}/invitations",
            headers=self.auth_headers,
        ).json()
        expired = next(item for item in invitations if item["id"] == invitation["id"])
        self.assertEqual(expired["status"], "expired")

    def test_async_run_job_completes_and_creates_run(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        enqueue = self.client.post(
            f"/api/workflows/{created['id']}/run-jobs",
            json={"input_text": "异步运行"},
            headers=self.auth_headers,
        )
        self.assertEqual(enqueue.status_code, 202)
        job = enqueue.json()
        for _ in range(30):
            latest = self.client.get(f"/api/run-jobs/{job['id']}", headers=self.auth_headers).json()
            if latest["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.1)
        self.assertEqual(latest["status"], "succeeded")
        self.assertTrue(latest["run_id"])
        run = self.client.get(f"/api/runs/{latest['run_id']}", headers=self.auth_headers)
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["input_text"], "异步运行")
        self.assertEqual(run.json()["workflow_version"], "0.2.0")
        self.assertEqual(run.json()["execution_mode"], "development")

    def test_run_job_uses_enqueue_time_workflow_snapshot(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        job = api.store.create_run_job(user["id"], workspace["id"], created["id"], "快照运行")

        changed = named_workflow("入队后改名")
        changed["nodes"][1]["data"]["prompt"] = "入队之后的新输出"
        update = self.client.put(
            f"/api/workflows/{created['id']}",
            json=changed,
            headers=self.auth_headers,
        )
        self.assertEqual(update.status_code, 200)

        snapshot = api.store.get_workflow_for_job(created["id"], job.id)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.name, valid_workflow()["name"])
        self.assertEqual(snapshot.nodes[1]["data"]["prompt"], "{{user_request}}")

    def test_interrupted_job_resumes_from_persisted_steps(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        job = api.store.create_run_job(user["id"], workspace["id"], created["id"], "续跑输入")
        claimed = api.store.claim_run_job(job.id)
        workflow = api.store.get_workflow_for_job(created["id"], job.id)
        run = api.store.ensure_run_for_job(job.id, workflow)
        api.store.update_run_progress(
            run.id,
            RunResponse(
                status="running",
                execution_mode="development",
                steps=[
                    RunStep(
                        node_id="input-1",
                        title="1. 用户输入",
                        status="done",
                        input="用户请求",
                        output="续跑输入",
                        kind="input",
                        variable="{{user_request}}",
                    )
                ],
            ),
        )

        self.assertEqual(api.store.requeue_interrupted_run_jobs(), 1)
        queue = RunJobQueue(api.store, backend="thread", execution_mode="development")
        self.assertTrue(queue.run_next_queued_job())

        latest = api.store.get_run_job(job.id, user["id"], workspace["id"])
        resumed = api.store.get_run(run.id, user["id"], workspace["id"])
        self.assertEqual(latest.status, "succeeded")
        self.assertEqual(latest.run_id, run.id)
        self.assertEqual(resumed.status, "ok")
        self.assertEqual([step.node_id for step in resumed.steps], ["input-1", "output-1"])

    def test_running_run_job_can_be_canceled_at_node_boundary(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        job = api.store.create_run_job(user["id"], workspace["id"], created["id"], "运行中取消")
        claimed = api.store.claim_run_job(job.id)
        workflow = api.store.get_workflow_for_job(created["id"], job.id)
        run = api.store.ensure_run_for_job(job.id, workflow)

        cancel = self.client.post(f"/api/run-jobs/{job.id}/cancel", headers=self.auth_headers)
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.json()["status"], "canceling")
        self.assertTrue(cancel.json()["cancel_requested"])

        RunJobQueue(api.store, backend="thread", execution_mode="development")._run_claimed_job(claimed)
        latest = api.store.get_run_job(job.id, user["id"], workspace["id"])
        canceled_run = api.store.get_run(run.id, user["id"], workspace["id"])
        self.assertEqual(latest.status, "canceled")
        self.assertEqual(canceled_run.status, "canceled")
        self.assertEqual(canceled_run.steps[-1].status, "canceled")

    def test_test_worker_claims_queued_job(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        queue = RunJobQueue(api.store, backend="thread")

        job = api.store.create_run_job(user["id"], workspace["id"], created["id"], "测试队列运行")
        self.assertEqual(job.status, "queued")

        self.assertTrue(queue.run_next_queued_job())
        latest = self.client.get(f"/api/run-jobs/{job.id}", headers=self.auth_headers).json()
        self.assertEqual(latest["status"], "succeeded")
        self.assertTrue(latest["run_id"])

    def test_queued_run_job_can_be_canceled(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        job = api.store.create_run_job(user["id"], workspace["id"], created["id"], "取消排队任务")

        canceled = self.client.post(f"/api/run-jobs/{job.id}/cancel", headers=self.auth_headers)

        self.assertEqual(canceled.status_code, 200)
        self.assertEqual(canceled.json()["status"], "canceled")
        self.assertIn("取消", canceled.json()["error"])
        self.assertIsNone(api.store.claim_run_job(job.id))

    def test_failed_run_job_can_be_retried_and_republished(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        job = api.store.create_run_job(user["id"], workspace["id"], created["id"], "重试失败任务")
        api.store.update_run_job(job.id, "failed", error="boom")

        class FakeFuture:
            def get(self, timeout=None):
                return None

        class FakeProducer:
            def __init__(self):
                self.messages = []

            def send(self, topic, value):
                self.messages.append((topic, value))
                return FakeFuture()

        producer = FakeProducer()
        api.job_queue = RunJobQueue(api.store, backend="kafka", kafka_producer=producer)

        retried = self.client.post(f"/api/run-jobs/{job.id}/retry", headers=self.auth_headers)

        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["status"], "queued")
        self.assertIsNone(retried.json()["error"])
        self.assertEqual(producer.messages, [(api.job_queue.kafka_topic, job.id)])

    def test_terminal_run_jobs_can_be_cleaned_without_touching_active_jobs(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        queued = api.store.create_run_job(user["id"], workspace["id"], created["id"], "排队任务")
        succeeded = api.store.create_run_job(user["id"], workspace["id"], created["id"], "成功任务")
        failed = api.store.create_run_job(user["id"], workspace["id"], created["id"], "失败任务")
        canceled = api.store.create_run_job(user["id"], workspace["id"], created["id"], "取消任务")
        api.store.update_run_job(succeeded.id, "succeeded", run_id="run-1")
        api.store.update_run_job(failed.id, "failed", error="boom")
        api.store.cancel_run_job(canceled.id, user["id"], workspace["id"])

        cleanup = self.client.delete(f"/api/run-jobs?workflow_id={created['id']}", headers=self.auth_headers)

        self.assertEqual(cleanup.status_code, 204)
        jobs = self.client.get(f"/api/run-jobs?workflow_id={created['id']}", headers=self.auth_headers).json()
        self.assertEqual([job["id"] for job in jobs], [queued.id])
        self.assertEqual(jobs[0]["status"], "queued")
        logs = self.client.get("/api/audit-logs?resource_type=run_job", headers=self.auth_headers).json()
        self.assertIn("run_job.cleanup", [log["action"] for log in logs])

    def test_kafka_queue_publishes_and_worker_claims_job(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]

        class FakeFuture:
            def get(self, timeout=None):
                return None

        class FakeProducer:
            def __init__(self):
                self.messages = []

            def send(self, topic, value):
                self.messages.append((topic, value))
                return FakeFuture()

        class FakeConsumer:
            def __init__(self, job_id):
                self.job_id = job_id
                self.committed = False

            def poll(self, timeout_ms=None, max_records=None):
                if not self.job_id:
                    return {}
                job_id = self.job_id
                self.job_id = ""
                return {"partition-0": [type("Message", (), {"value": job_id})()]}

            def commit(self):
                self.committed = True

        producer = FakeProducer()
        queue = RunJobQueue(api.store, backend="kafka", kafka_producer=producer)
        job = queue.enqueue(user["id"], workspace["id"], created["id"], "Kafka 队列运行")

        self.assertEqual(producer.messages, [(queue.kafka_topic, job.id)])
        queue.kafka_consumer = FakeConsumer(job.id)
        worker = RunJobWorker(queue)

        self.assertTrue(worker._run_once())
        self.assertTrue(queue.kafka_consumer.committed)
        latest = self.client.get(f"/api/run-jobs/{job.id}", headers=self.auth_headers).json()
        self.assertEqual(latest["status"], "succeeded")
        self.assertTrue(latest["run_id"])

    def test_interrupted_jobs_are_requeued_for_worker_restart(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        job = api.store.create_run_job(user["id"], workspace["id"], created["id"], "重启恢复")

        claimed = api.store.claim_run_job(job.id)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.status, "running")

        self.assertEqual(api.store.requeue_interrupted_run_jobs(), 1)
        latest = self.client.get(f"/api/run-jobs/{job.id}", headers=self.auth_headers).json()
        self.assertEqual(latest["status"], "queued")
        self.assertIn("重新入队", latest["error"])

    def test_workspace_knowledge_upload_indexes_and_searches(self) -> None:
        upload = self.client.post(
            "/api/knowledge/documents",
            json={"filename": "vector-test.md", "content": "退款通常会在三到五个工作日到账。"},
            headers=self.auth_headers,
        )
        self.assertEqual(upload.status_code, 201)
        status = self.client.get("/api/knowledge/status", headers=self.auth_headers).json()
        self.assertGreaterEqual(status["indexed_chunk_count"], 1)

        workflow = {
            **valid_workflow(),
            "nodes": [
                {
                    "id": "input-1",
                    "position": {"x": 0, "y": 0},
                    "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                },
                {
                    "id": "knowledge-1",
                    "position": {"x": 240, "y": 0},
                    "data": {
                        "kind": "knowledge",
                        "label": "知识检索",
                        "query": "{{user_request}}",
                        "topK": 1,
                        "outputKey": "context",
                    },
                },
                {
                    "id": "output-1",
                    "position": {"x": 480, "y": 0},
                    "data": {"kind": "output", "label": "最终输出", "prompt": "{{context}}", "outputKey": "answer"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "input-1", "target": "knowledge-1"},
                {"id": "e2", "source": "knowledge-1", "target": "output-1"},
            ],
        }
        run = self.client.post(
            "/api/runs",
            json={"workflow": workflow, "input_text": "多久到账"},
            headers=self.auth_headers,
        ).json()
        self.assertIn("退款", run["steps"][1]["output"])

    def test_knowledge_node_can_use_paismart_adapter(self) -> None:
        def fake_search_paismart(query: str, top_k: int, runtime_config=None):
            from server.src.knowledge import KnowledgeChunk

            self.assertEqual(query, "外部检索")
            self.assertEqual(top_k, 2)
            return [KnowledgeChunk(source="pai-doc#1", text="PaiSmart 返回的企业知识片段", score=0.98)]

        runner.search_paismart = fake_search_paismart
        workflow = {
            **valid_workflow(),
            "nodes": [
                {
                    "id": "input-1",
                    "position": {"x": 0, "y": 0},
                    "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                },
                {
                    "id": "knowledge-1",
                    "position": {"x": 240, "y": 0},
                    "data": {
                        "kind": "knowledge",
                        "label": "PaiSmart 检索",
                        "knowledgeProvider": "paismart",
                        "query": "{{user_request}}",
                        "topK": 2,
                        "outputKey": "context",
                    },
                },
                {
                    "id": "output-1",
                    "position": {"x": 480, "y": 0},
                    "data": {"kind": "output", "label": "最终输出", "prompt": "{{context}}", "outputKey": "answer"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "input-1", "target": "knowledge-1"},
                {"id": "e2", "source": "knowledge-1", "target": "output-1"},
            ],
        }

        run = self.client.post(
            "/api/runs",
            json={"workflow": workflow, "input_text": "外部检索"},
            headers=self.auth_headers,
        ).json()
        knowledge_step = run["steps"][1]
        self.assertEqual(knowledge_step["provider"], "PaiSmart RAG")
        self.assertIn("PaiSmart 返回的企业知识片段", knowledge_step["output"])

    def test_workspace_paismart_config_is_used_by_knowledge_runner(self) -> None:
        save_response = self.client.put(
            "/api/model-configs/paismart",
            json={
                "enabled": True,
                "model": "hybrid",
                "base_url": "http://paismart.test",
                "api_key": "paismart-workspace-token",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(save_response.status_code, 200)
        saved = save_response.json()
        self.assertTrue(saved["has_api_key"])
        self.assertNotIn("paismart-workspace-token", str(saved))

        test_response = self.client.post("/api/model-configs/paismart/test", headers=self.auth_headers)
        self.assertEqual(test_response.status_code, 200)
        self.assertTrue(test_response.json()["ok"])

        captured = {}

        def fake_search_paismart(query: str, top_k: int, runtime_config=None):
            from server.src.knowledge import KnowledgeChunk

            captured["runtime_config"] = runtime_config
            return [KnowledgeChunk(source="pai-doc#1", text="团队空间 PaiSmart 片段", score=0.99)]

        previous = runner.search_paismart
        runner.search_paismart = fake_search_paismart
        try:
            workflow = {
                **valid_workflow(),
                "nodes": [
                    {
                        "id": "input-1",
                        "position": {"x": 0, "y": 0},
                        "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                    },
                    {
                        "id": "knowledge-1",
                        "position": {"x": 240, "y": 0},
                        "data": {
                            "kind": "knowledge",
                            "label": "PaiSmart 检索",
                            "knowledgeProvider": "paismart",
                            "query": "{{user_request}}",
                            "topK": 1,
                            "outputKey": "context",
                        },
                    },
                    {
                        "id": "output-1",
                        "position": {"x": 480, "y": 0},
                        "data": {"kind": "output", "label": "最终输出", "prompt": "{{context}}", "outputKey": "answer"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "input-1", "target": "knowledge-1"},
                    {"id": "e2", "source": "knowledge-1", "target": "output-1"},
                ],
            }
            run = self.client.post(
                "/api/runs",
                json={"workflow": workflow, "input_text": "团队空间检索"},
                headers=self.auth_headers,
            ).json()
        finally:
            runner.search_paismart = previous

        self.assertEqual(run["steps"][1]["provider"], "PaiSmart RAG")
        self.assertIn("团队空间 PaiSmart 片段", run["steps"][1]["output"])
        self.assertEqual(captured["runtime_config"]["api_key"], "paismart-workspace-token")
        self.assertEqual(captured["runtime_config"]["base_url"], "http://paismart.test")

    def test_paismart_preview_uses_workspace_config(self) -> None:
        self.client.put(
            "/api/model-configs/paismart",
            json={
                "enabled": True,
                "model": "hybrid",
                "base_url": "http://paismart.test",
                "api_key": "paismart-preview-token",
            },
            headers=self.auth_headers,
        )

        from server.src import main as api_module
        from server.src.knowledge import KnowledgeChunk

        captured = {}

        def fake_search_paismart(query: str, top_k: int, runtime_config=None):
            captured["query"] = query
            captured["top_k"] = top_k
            captured["runtime_config"] = runtime_config
            return [KnowledgeChunk(source="doc.md#1", text="预览返回片段", score=0.88)]

        previous = api_module.search_paismart
        api_module.search_paismart = fake_search_paismart
        try:
            response = self.client.post(
                "/api/rag/paismart/preview",
                json={"query": "报销需要什么", "top_k": 2},
                headers=self.auth_headers,
            )
        finally:
            api_module.search_paismart = previous

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["text"], "预览返回片段")
        self.assertEqual(captured["query"], "报销需要什么")
        self.assertEqual(captured["top_k"], 2)
        self.assertEqual(captured["runtime_config"]["api_key"], "paismart-preview-token")

    def test_paismart_diagnose_reports_connection_status(self) -> None:
        self.client.put(
            "/api/model-configs/paismart",
            json={
                "enabled": True,
                "model": "hybrid",
                "base_url": "http://paismart.test",
                "api_key": "paismart-diagnose-token",
            },
            headers=self.auth_headers,
        )

        from server.src import main as api_module
        from server.src.knowledge import KnowledgeChunk

        captured = {}

        def fake_search_paismart(query: str, top_k: int, runtime_config=None):
            captured["query"] = query
            captured["top_k"] = top_k
            captured["runtime_config"] = runtime_config
            return [KnowledgeChunk(source="doc.md#1", text="诊断片段", score=0.8)]

        previous = api_module.search_paismart
        api_module.search_paismart = fake_search_paismart
        try:
            response = self.client.post("/api/rag/paismart/diagnose", headers=self.auth_headers)
        finally:
            api_module.search_paismart = previous

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["base_url"], "http://paismart.test")
        self.assertTrue(body["token_configured"])
        self.assertEqual(body["result_count"], 1)
        self.assertEqual(captured["query"], "连接诊断")
        self.assertEqual(captured["runtime_config"]["api_key"], "paismart-diagnose-token")

    def test_aliyun_multimodal_nodes_fall_back_without_key(self) -> None:
        workflow = {
            **valid_workflow(),
            "nodes": [
                {
                    "id": "input-1",
                    "position": {"x": 0, "y": 0},
                    "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                },
                {
                    "id": "tts-1",
                    "position": {"x": 240, "y": 0},
                    "data": {
                        "kind": "tts",
                        "label": "语音播报",
                        "ttsText": "{{user_request}}",
                        "ttsModel": "cosyvoice-v2",
                        "ttsVoice": "longxiaochun",
                        "audioFormat": "mp3",
                        "speechRate": 1,
                        "outputKey": "audio_url",
                    },
                },
                {
                    "id": "image-1",
                    "position": {"x": 480, "y": 0},
                    "data": {
                        "kind": "image",
                        "label": "配图生成",
                        "imagePrompt": "给 {{user_request}} 生成一张配图",
                        "imageModel": "wanx2.1-t2i-turbo",
                        "imageSize": "1024*1024",
                        "imageCount": 1,
                        "outputKey": "image_urls",
                    },
                },
                {
                    "id": "output-1",
                    "position": {"x": 720, "y": 0},
                    "data": {
                        "kind": "output",
                        "label": "最终输出",
                        "prompt": "{{audio_url}}\n{{image_urls}}",
                        "outputKey": "answer",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "input-1", "target": "tts-1"},
                {"id": "e2", "source": "tts-1", "target": "image-1"},
                {"id": "e3", "source": "image-1", "target": "output-1"},
            ],
        }

        run = self.client.post(
            "/api/runs",
            json={"workflow": workflow, "input_text": "新品发布"},
            headers=self.auth_headers,
        )
        self.assertEqual(run.status_code, 200)
        steps = run.json()["steps"]
        self.assertEqual(steps[1]["provider"], "模拟输出")
        self.assertIn("阿里云 TTS 未配置 Key", steps[1]["output"])
        self.assertEqual(steps[2]["provider"], "模拟输出")
        self.assertIn("阿里云图片生成未配置 Key", steps[2]["output"])

    def test_json_llm_template_falls_back_to_parseable_json_without_key(self) -> None:
        previous_deepseek = os.environ.pop("DEEPSEEK_API_KEY", None)
        previous_openai = os.environ.pop("OPENAI_API_KEY", None)
        workflow = {
            **valid_workflow(),
            "nodes": [
                {
                    "id": "input-1",
                    "position": {"x": 0, "y": 0},
                    "data": {"kind": "input", "label": "素材需求", "outputKey": "campaign_request"},
                },
                {
                    "id": "llm-1",
                    "position": {"x": 260, "y": 0},
                    "data": {
                        "kind": "llm",
                        "label": "生成素材 JSON",
                        "model": "deepseek-v4-flash",
                        "prompt": (
                            "根据需求输出严格 JSON，字段必须包含 title、script、image_prompt、caption、publish_checklist。"
                            "需求：{{campaign_request}}"
                        ),
                        "outputKey": "content_json",
                    },
                },
                {
                    "id": "json-script",
                    "position": {"x": 520, "y": 0},
                    "data": {
                        "kind": "json",
                        "label": "提取口播",
                        "jsonSource": "{{content_json}}",
                        "jsonPath": "script",
                        "outputKey": "script",
                    },
                },
                {
                    "id": "output-1",
                    "position": {"x": 780, "y": 0},
                    "data": {"kind": "output", "label": "最终输出", "prompt": "{{script}}", "outputKey": "answer"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "input-1", "target": "llm-1"},
                {"id": "e2", "source": "llm-1", "target": "json-script"},
                {"id": "e3", "source": "json-script", "target": "output-1"},
            ],
        }
        try:
            run = self.client.post(
                "/api/runs",
                json={
                    "workflow": workflow,
                    "input_text": "为咖啡店新品燕麦拿铁生成一套短视频素材，面向上班族。",
                },
                headers=self.auth_headers,
            )
        finally:
            if previous_deepseek is not None:
                os.environ["DEEPSEEK_API_KEY"] = previous_deepseek
            if previous_openai is not None:
                os.environ["OPENAI_API_KEY"] = previous_openai

        self.assertEqual(run.status_code, 200)
        body = run.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["steps"][1]["provider"], "模拟输出")
        self.assertEqual(body["steps"][1]["status"], "degraded")
        self.assertEqual(body["steps"][2]["status"], "done")
        self.assertIn("燕麦拿铁", body["steps"][3]["output"])

    def test_production_mode_rejects_simulated_llm_output(self) -> None:
        workflow = WorkflowPayload(
            **{
                **valid_workflow(),
                "nodes": [
                    valid_workflow()["nodes"][0],
                    {
                        "id": "llm-1",
                        "position": {"x": 240, "y": 0},
                        "data": {
                            "kind": "llm",
                            "label": "真实模型必需",
                            "prompt": "{{user_request}}",
                            "outputKey": "draft",
                        },
                    },
                    valid_workflow()["nodes"][1],
                ],
                "edges": [
                    {"id": "e1", "source": "input-1", "target": "llm-1"},
                    {"id": "e2", "source": "llm-1", "target": "output-1"},
                ],
            }
        )
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = runner.simulate_run(workflow, "必须真实调用", execution_mode="production")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.execution_mode, "production")
        self.assertEqual(result.steps[1].status, "error")
        self.assertEqual(result.steps[1].provider, "生产模式已阻止模拟输出")
        self.assertIn("生产模式禁止模拟", result.steps[1].error)

    def test_progress_callback_reports_running_node_before_completion(self) -> None:
        events: list[RunResponse] = []
        result = runner.simulate_run(
            WorkflowPayload(**valid_workflow()),
            "进度测试",
            execution_mode="development",
            progress_callback=events.append,
            run_id="run-progress-test",
        )

        self.assertEqual(result.status, "ok")
        self.assertTrue(any(step.status == "running" for event in events for step in event.steps))
        self.assertEqual(events[-1].status, "ok")

    def test_orchestration_nodes_transform_and_aggregate_context(self) -> None:
        workflow = {
            **valid_workflow(),
            "nodes": [
                {
                    "id": "input-1",
                    "position": {"x": 0, "y": 0},
                    "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                },
                {
                    "id": "assign-1",
                    "position": {"x": 220, "y": 0},
                    "data": {
                        "kind": "assign",
                        "label": "变量赋值",
                        "assignmentValue": '{"items":["{{user_request}}","复盘"]}',
                        "outputKey": "raw_json",
                    },
                },
                {
                    "id": "json-1",
                    "position": {"x": 440, "y": 0},
                    "data": {"kind": "json", "label": "JSON 解析", "jsonSource": "{{raw_json}}", "jsonPath": "items", "outputKey": "items"},
                },
                {
                    "id": "loop-1",
                    "position": {"x": 660, "y": 0},
                    "data": {
                        "kind": "loop",
                        "label": "循环迭代",
                        "loopItems": "{{items}}",
                        "loopTemplate": "{{index}}. {{item}}",
                        "loopSeparator": "\n",
                        "outputKey": "loop_result",
                    },
                },
                {
                    "id": "code-1",
                    "position": {"x": 880, "y": 0},
                    "data": {"kind": "code", "label": "代码执行", "codeExpression": "upper(user_request)", "outputKey": "upper_text"},
                },
                {
                    "id": "template-1",
                    "position": {"x": 1100, "y": 0},
                    "data": {"kind": "template", "label": "文本模板", "templateText": "{{loop_result}}\n{{upper_text}}", "outputKey": "templated"},
                },
                {
                    "id": "aggregate-1",
                    "position": {"x": 1320, "y": 0},
                    "data": {
                        "kind": "aggregate",
                        "label": "结果聚合",
                        "aggregateVariables": "templated, upper_text",
                        "aggregateSeparator": "\n---\n",
                        "outputKey": "answer",
                    },
                },
                {
                    "id": "output-1",
                    "position": {"x": 1540, "y": 0},
                    "data": {"kind": "output", "label": "最终回答", "prompt": "{{answer}}", "outputKey": "final"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "input-1", "target": "assign-1"},
                {"id": "e2", "source": "assign-1", "target": "json-1"},
                {"id": "e3", "source": "json-1", "target": "loop-1"},
                {"id": "e4", "source": "loop-1", "target": "code-1"},
                {"id": "e5", "source": "code-1", "target": "template-1"},
                {"id": "e6", "source": "template-1", "target": "aggregate-1"},
                {"id": "e7", "source": "aggregate-1", "target": "output-1"},
            ],
        }

        run = self.client.post(
            "/api/runs",
            json={"workflow": workflow, "input_text": "hello"},
            headers=self.auth_headers,
        )
        self.assertEqual(run.status_code, 200)
        steps = run.json()["steps"]
        self.assertEqual(steps[-1]["output"], "1. hello\n2. 复盘\nHELLO\n---\nHELLO")

    def test_workspace_model_config_masks_key_and_is_used_by_runner(self) -> None:
        save_response = self.client.put(
            "/api/model-configs/deepseek",
            json={
                "enabled": True,
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-test-workspace-key",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(save_response.status_code, 200)
        saved = save_response.json()
        self.assertTrue(saved["has_api_key"])
        self.assertNotIn("sk-test-workspace-key", str(saved))

        test_response = self.client.post("/api/model-configs/deepseek/test", headers=self.auth_headers)
        self.assertEqual(test_response.status_code, 200)
        self.assertTrue(test_response.json()["ok"])

        captured = {}

        def fake_deepseek_node(data, system_prompt, prompt, runtime_config=None):
            captured["runtime_config"] = runtime_config
            return "工作区模型输出", runtime_config["model"]

        previous = runner.run_deepseek_node
        runner.run_deepseek_node = fake_deepseek_node
        try:
            workflow = {
                **valid_workflow(),
                "nodes": [
                    {
                        "id": "input-1",
                        "position": {"x": 0, "y": 0},
                        "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                    },
                    {
                        "id": "llm-1",
                        "position": {"x": 240, "y": 0},
                        "data": {
                            "kind": "llm",
                            "label": "模型节点",
                            "prompt": "{{user_request}}",
                            "outputKey": "draft",
                        },
                    },
                    {
                        "id": "output-1",
                        "position": {"x": 480, "y": 0},
                        "data": {"kind": "output", "label": "最终输出", "prompt": "{{draft}}", "outputKey": "answer"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "input-1", "target": "llm-1"},
                    {"id": "e2", "source": "llm-1", "target": "output-1"},
                ],
            }
            run = self.client.post(
                "/api/runs",
                json={"workflow": workflow, "input_text": "使用团队空间模型"},
                headers=self.auth_headers,
            ).json()
        finally:
            runner.run_deepseek_node = previous

        llm_step = run["steps"][1]
        self.assertEqual(llm_step["provider"], "DeepSeek 工作区配置 - deepseek-v4-flash")
        self.assertEqual(captured["runtime_config"]["api_key"], "sk-test-workspace-key")

    def test_workspace_aliyun_config_masks_key_and_is_used_by_tts_runner(self) -> None:
        save_response = self.client.put(
            "/api/model-configs/aliyun",
            json={
                "enabled": True,
                "model": "cosyvoice-v2",
                "base_url": "https://dashscope.aliyuncs.com",
                "api_key": "sk-aliyun-workspace-key",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(save_response.status_code, 200)
        saved = save_response.json()
        self.assertTrue(saved["has_api_key"])
        self.assertNotIn("sk-aliyun-workspace-key", str(saved))

        test_response = self.client.post("/api/model-configs/aliyun/test", headers=self.auth_headers)
        self.assertEqual(test_response.status_code, 200)
        self.assertTrue(test_response.json()["ok"])

        captured = {}

        def fake_run_tts(text, model="cosyvoice-v2", voice="longxiaochun_v2", audio_format="mp3", speech_rate=1.0, runtime_config=None):
            captured["runtime_config"] = runtime_config
            captured["model"] = model
            return "https://example.test/audio.mp3", model

        previous = runner.run_tts
        runner.run_tts = fake_run_tts
        try:
            workflow = {
                **valid_workflow(),
                "nodes": [
                    {
                        "id": "input-1",
                        "position": {"x": 0, "y": 0},
                        "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
                    },
                    {
                        "id": "tts-1",
                        "position": {"x": 240, "y": 0},
                        "data": {
                            "kind": "tts",
                            "label": "文字转语音",
                            "ttsText": "{{user_request}}",
                            "outputKey": "audio",
                        },
                    },
                    {
                        "id": "output-1",
                        "position": {"x": 480, "y": 0},
                        "data": {"kind": "output", "label": "最终输出", "prompt": "{{audio}}", "outputKey": "answer"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "input-1", "target": "tts-1"},
                    {"id": "e2", "source": "tts-1", "target": "output-1"},
                ],
            }
            run = self.client.post(
                "/api/runs",
                json={"workflow": workflow, "input_text": "欢迎使用工作流"},
                headers=self.auth_headers,
            ).json()
        finally:
            runner.run_tts = previous

        tts_step = run["steps"][1]
        self.assertEqual(tts_step["provider"], "阿里云 TTS - cosyvoice-v2")
        self.assertEqual(captured["runtime_config"]["api_key"], "sk-aliyun-workspace-key")
        self.assertEqual(captured["model"], "cosyvoice-v2")

    def test_aliyun_tts_uses_speech_synthesizer_endpoint(self) -> None:
        captured = {}

        def fake_request_json(path, payload=None, headers=None, runtime_config=None):
            captured["path"] = path
            captured["payload"] = payload
            captured["headers"] = headers
            captured["runtime_config"] = runtime_config
            return {"output": {"audio_url": "https://example.test/audio.mp3"}}

        previous = aliyun._request_json
        aliyun._request_json = fake_request_json
        try:
            audio_url, model = aliyun.run_tts(
                "欢迎使用工作流",
                "cosyvoice-v2",
                "longxiaochun",
                "mp3",
                1.2,
                {"api_key": "sk-test", "base_url": "https://dashscope.aliyuncs.com"},
            )
        finally:
            aliyun._request_json = previous

        self.assertEqual(audio_url, "https://example.test/audio.mp3")
        self.assertEqual(model, "cosyvoice-v2")
        self.assertEqual(captured["path"], "/api/v1/services/audio/tts/SpeechSynthesizer")
        self.assertEqual(captured["payload"]["input"]["text"], "欢迎使用工作流")
        self.assertEqual(captured["payload"]["input"]["voice"], "longxiaochun_v2")
        self.assertEqual(captured["payload"]["input"]["format"], "mp3")
        self.assertEqual(captured["payload"]["input"]["rate"], 1.2)

    def test_aliyun_tts_clamps_speech_rate_as_multiplier(self) -> None:
        captured_rates = []

        def fake_request_json(path, payload=None, headers=None, runtime_config=None):
            captured_rates.append(payload["input"]["rate"])
            return {"output": {"audio_url": "https://example.test/audio.mp3"}}

        previous = aliyun._request_json
        aliyun._request_json = fake_request_json
        try:
            aliyun.run_tts("慢速", speech_rate=0.2, runtime_config={"api_key": "sk-test"})
            aliyun.run_tts("快速", speech_rate=4.0, runtime_config={"api_key": "sk-test"})
        finally:
            aliyun._request_json = previous

        self.assertEqual(captured_rates, [0.5, 2.0])

    def test_aliyun_tts_keeps_v1_voice_for_v1_model(self) -> None:
        captured = {}

        def fake_request_json(path, payload=None, headers=None, runtime_config=None):
            captured["payload"] = payload
            return {"output": {"audio_url": "https://example.test/audio.mp3"}}

        previous = aliyun._request_json
        aliyun._request_json = fake_request_json
        try:
            aliyun.run_tts("欢迎使用工作流", "cosyvoice-v1", "longxiaochun", "mp3", 1.0, {"api_key": "sk-test"})
        finally:
            aliyun._request_json = previous

        self.assertEqual(captured["payload"]["input"]["voice"], "longxiaochun")


if __name__ == "__main__":
    unittest.main()
