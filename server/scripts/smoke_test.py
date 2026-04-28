import urllib.request
import json
from urllib.error import HTTPError


BASE_URL = "http://127.0.0.1:8000"


def request(path: str, method: str = "GET", body: dict | None = None) -> dict | list:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        content = response.read().decode("utf-8")
        return json.loads(content) if content else {}


def request_error(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    try:
        request(path, method, body)
    except HTTPError as error:
        content = error.read().decode("utf-8")
        return error.code, json.loads(content) if content else {}
    raise AssertionError(f"Expected {method} {path} to fail")


def main() -> None:
    health = request("/api/health")
    workflow = {
        "name": "Smoke Test Workflow",
        "version": "0.2.0",
        "nodes": [
            {
                "id": "input-1",
                "position": {"x": 0, "y": 0},
                "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
            },
            {
                "id": "llm-1",
                "position": {"x": 150, "y": 0},
                "data": {
                    "kind": "llm",
                    "label": "大模型草稿",
                    "model": "gpt-5.4-mini",
                    "systemPrompt": "你是测试助手。",
                    "prompt": "请回复：{{user_request}}",
                    "outputKey": "draft",
                },
            },
            {
                "id": "output-1",
                "position": {"x": 300, "y": 0},
                "data": {
                    "kind": "output",
                    "label": "最终回答",
                    "prompt": "收到：{{draft}}",
                    "outputKey": "answer",
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "input-1", "target": "llm-1"},
            {"id": "e2", "source": "llm-1", "target": "output-1"},
        ],
    }
    invalid_workflow = {
        "name": "Invalid Smoke Test Workflow",
        "version": "0.2.0",
        "nodes": [
            {
                "id": "output-1",
                "position": {"x": 0, "y": 0},
                "data": {"kind": "output", "label": "最终回答", "outputKey": "answer"},
            }
        ],
        "edges": [],
    }
    validation = request("/api/workflows/validate", "POST", workflow)
    invalid_validation = request("/api/workflows/validate", "POST", invalid_workflow)
    invalid_create_status, invalid_create_body = request_error("/api/workflows", "POST", invalid_workflow)
    invalid_run_status, invalid_run_body = request_error(
        "/api/runs",
        "POST",
        {"workflow": invalid_workflow, "input_text": "无效运行"},
    )
    created = request("/api/workflows", "POST", workflow)
    run = request("/api/runs", "POST", {"workflow": workflow, "input_text": "测试输入"})
    stored_run = request(f"/api/workflows/{created['id']}/runs", "POST", {"input_text": "后端历史测试"})
    runs = request("/api/runs")
    workflow_runs = request(f"/api/runs?workflow_id={created['id']}")
    fetched_run = request(f"/api/runs/{stored_run['id']}")
    delete_single_result = request(f"/api/runs/{stored_run['id']}", "DELETE")
    deleted_single_status, _ = request_error(f"/api/runs/{stored_run['id']}")
    second_stored_run = request(f"/api/workflows/{created['id']}/runs", "POST", {"input_text": "清理历史测试"})
    delete_workflow_runs_result = request(f"/api/runs?workflow_id={created['id']}", "DELETE")
    workflow_runs_after_clear = request(f"/api/runs?workflow_id={created['id']}")

    assert validation["valid"] is True
    assert invalid_validation["valid"] is False
    assert invalid_create_status == 400
    assert invalid_create_body["detail"]["valid"] is False
    assert invalid_run_status == 400
    assert invalid_run_body["detail"]["valid"] is False
    assert any(
        step.get("provider") == "模拟输出"
        or str(step.get("provider", "")).startswith("OpenAI")
        or str(step.get("provider", "")).startswith("DeepSeek")
        for step in run["steps"]
    )
    assert len(workflow_runs) >= 1
    assert all(run["workflow_id"] == created["id"] for run in workflow_runs)
    assert delete_single_result == {}
    assert deleted_single_status == 404
    assert second_stored_run["workflow_id"] == created["id"]
    assert delete_workflow_runs_result == {}
    assert workflow_runs_after_clear == []

    print(
        json.dumps(
            {
                "health": health,
                "validation_valid": validation["valid"],
                "invalid_validation_valid": invalid_validation["valid"],
                "invalid_create_status": invalid_create_status,
                "invalid_run_status": invalid_run_status,
                "created_id": created["id"],
                "run_status": run["status"],
                "step_count": len(run["steps"]),
                "llm_provider": next((step.get("provider") for step in run["steps"] if step.get("provider")), None),
                "stored_run_id": stored_run["id"],
                "run_count": len(runs),
                "workflow_run_count": len(workflow_runs),
                "deleted_single_status": deleted_single_status,
                "workflow_runs_after_clear": len(workflow_runs_after_clear),
                "fetched_run_status": fetched_run["status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
