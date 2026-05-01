import logging
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.src.auth import AuthService, set_auth_service
from server.src import main as api
from server.src import runner
from server.src.db import create_session_factory
from server.src.jobs import RunJobQueue
from server.src.knowledge import set_knowledge_session_factory
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


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls) -> None:
        logging.disable(logging.NOTSET)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.previous_store = api.store
        self.previous_auth_service = api.auth_service
        test_db = Path(self.temp_dir.name) / "test.db"
        engine, session_factory = create_session_factory(f"sqlite:///{test_db.as_posix()}")
        self.engine = engine
        self.previous_search_paismart = runner.search_paismart
        api.store = WorkflowStore(test_db, session_factory=session_factory, engine=engine)
        set_knowledge_session_factory(api.store.SessionLocal)
        api.job_queue = RunJobQueue(api.store)
        api.auth_service = AuthService(api.store)
        set_auth_service(api.auth_service)
        self.client = TestClient(api.app)
        self.auth_headers = self.create_auth_headers()

    def tearDown(self) -> None:
        self.client.close()
        self.engine.dispose()
        api.store = self.previous_store
        set_knowledge_session_factory(api.store.SessionLocal)
        api.job_queue = RunJobQueue(api.store)
        api.auth_service = self.previous_auth_service
        set_auth_service(self.previous_auth_service)
        runner.search_paismart = self.previous_search_paismart
        self.temp_dir.cleanup()

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
        self.assertEqual(response.json(), {"status": "ok"})

    def test_rejects_invalid_workflow(self) -> None:
        response = self.client.post("/api/workflows", json=invalid_workflow(), headers=self.auth_headers)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["detail"]["valid"])

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
        def fake_search_paismart(query: str, top_k: int):
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


if __name__ == "__main__":
    unittest.main()
