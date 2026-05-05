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
from server.src.orm import DbSession
from server.src.providers import aliyun
from server.src.db import create_session_factory
from server.src.jobs import RunJobQueue, RunJobWorker
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
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "sqlite")
        self.assertEqual(body["queue_backend"], "thread")

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

    def test_database_worker_claims_queued_job(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow(), headers=self.auth_headers).json()
        user = self.client.get("/api/auth/me", headers=self.auth_headers).json()
        workspace = self.client.get("/api/workspaces", headers=self.auth_headers).json()[0]
        queue = RunJobQueue(api.store, backend="database")

        job = queue.enqueue(user["id"], workspace["id"], created["id"], "数据库队列运行")
        self.assertEqual(job.status, "queued")

        self.assertTrue(queue.run_next_queued_job())
        latest = self.client.get(f"/api/run-jobs/{job.id}", headers=self.auth_headers).json()
        self.assertEqual(latest["status"], "succeeded")
        self.assertTrue(latest["run_id"])

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

        queue = RunJobQueue(api.store, backend="database")
        queue.backend = "kafka"
        producer = FakeProducer()
        queue.kafka_producer = producer
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
        self.assertEqual(captured["payload"]["input"]["rate"], 120)

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
