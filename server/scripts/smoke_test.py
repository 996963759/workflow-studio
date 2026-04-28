import urllib.request
import json


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
                "id": "output-1",
                "position": {"x": 300, "y": 0},
                "data": {
                    "kind": "output",
                    "label": "最终回答",
                    "prompt": "收到：{{user_request}}",
                    "outputKey": "answer",
                },
            },
        ],
        "edges": [{"id": "e1", "source": "input-1", "target": "output-1"}],
    }
    created = request("/api/workflows", "POST", workflow)
    run = request("/api/runs", "POST", {"workflow": workflow, "input_text": "测试输入"})
    stored_run = request(f"/api/workflows/{created['id']}/runs", "POST", {"input_text": "后端历史测试"})
    runs = request("/api/runs")
    fetched_run = request(f"/api/runs/{stored_run['id']}")
    print(
        json.dumps(
            {
                "health": health,
                "created_id": created["id"],
                "run_status": run["status"],
                "step_count": len(run["steps"]),
                "stored_run_id": stored_run["id"],
                "run_count": len(runs),
                "fetched_run_status": fetched_run["status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
