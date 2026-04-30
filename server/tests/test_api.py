import logging
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.src import main as api
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
        api.store = WorkflowStore(Path(self.temp_dir.name) / "test.db")
        self.client = TestClient(api.app)

    def tearDown(self) -> None:
        self.client.close()
        api.store = self.previous_store
        self.temp_dir.cleanup()

    def test_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_rejects_invalid_workflow(self) -> None:
        response = self.client.post("/api/workflows", json=invalid_workflow())
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["detail"]["valid"])

    def test_workflow_crud_persists_archive_state(self) -> None:
        create_response = self.client.post("/api/workflows", json=valid_workflow())
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertFalse(created["archived"])

        payload = {**valid_workflow(), "archived": True}
        update_response = self.client.put(f"/api/workflows/{created['id']}", json=payload)
        self.assertEqual(update_response.status_code, 200)
        self.assertTrue(update_response.json()["archived"])

        fetch_response = self.client.get(f"/api/workflows/{created['id']}")
        self.assertEqual(fetch_response.status_code, 200)
        self.assertTrue(fetch_response.json()["archived"])

    def test_deleting_workflow_deletes_runs(self) -> None:
        created = self.client.post("/api/workflows", json=valid_workflow()).json()
        run_response = self.client.post(
            f"/api/workflows/{created['id']}/runs",
            json={"input_text": "单元测试"},
        )
        self.assertEqual(run_response.status_code, 201)

        runs_before_delete = self.client.get(f"/api/runs?workflow_id={created['id']}").json()
        self.assertEqual(len(runs_before_delete), 1)

        delete_response = self.client.delete(f"/api/workflows/{created['id']}")
        self.assertEqual(delete_response.status_code, 204)

        self.assertEqual(self.client.get(f"/api/workflows/{created['id']}").status_code, 404)
        runs_after_delete = self.client.get(f"/api/runs?workflow_id={created['id']}").json()
        self.assertEqual(runs_after_delete, [])


if __name__ == "__main__":
    unittest.main()
