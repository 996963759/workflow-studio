import urllib.request
import json
import os
from urllib.error import HTTPError


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


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


def branch_workflow() -> dict:
    return {
        "name": "Branch Smoke Test Workflow",
        "version": "0.2.0",
        "nodes": [
            {
                "id": "input-1",
                "position": {"x": 0, "y": 0},
                "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
            },
            {
                "id": "condition-1",
                "position": {"x": 240, "y": 0},
                "data": {
                    "kind": "condition",
                    "label": "是否退款",
                    "conditionVariable": "user_request",
                    "conditionOperator": "contains",
                    "conditionValue": "退款",
                },
            },
            {
                "id": "true-output",
                "position": {"x": 520, "y": -80},
                "data": {"kind": "output", "label": "退款回复", "prompt": "退款流程", "outputKey": "refund_answer"},
            },
            {
                "id": "false-output",
                "position": {"x": 520, "y": 90},
                "data": {"kind": "output", "label": "普通回复", "prompt": "普通流程", "outputKey": "normal_answer"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input-1", "target": "condition-1"},
            {
                "id": "e-true",
                "source": "condition-1",
                "sourceHandle": "true",
                "target": "true-output",
            },
            {
                "id": "e-false",
                "source": "condition-1",
                "sourceHandle": "false",
                "target": "false-output",
            },
        ],
    }


def http_tool_workflow() -> dict:
    return {
        "name": "HTTP Tool Smoke Test Workflow",
        "version": "0.2.0",
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
                    "label": "健康检查",
                    "toolName": "health.check",
                    "toolUrl": f"{BASE_URL}/api/health",
                    "toolMethod": "GET",
                    "toolHeaders": "{}",
                    "toolParams": "{}",
                    "outputKey": "tool_result",
                },
            },
            {
                "id": "output-1",
                "position": {"x": 520, "y": 0},
                "data": {"kind": "output", "label": "最终回答", "prompt": "{{tool_result}}", "outputKey": "answer"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input-1", "target": "tool-1"},
            {"id": "e2", "source": "tool-1", "target": "output-1"},
        ],
    }


def knowledge_workflow() -> dict:
    return {
        "name": "Knowledge Smoke Test Workflow",
        "version": "0.2.0",
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
                    "topK": 2,
                    "outputKey": "context",
                },
            },
            {
                "id": "output-1",
                "position": {"x": 520, "y": 0},
                "data": {"kind": "output", "label": "最终回答", "prompt": "{{context}}", "outputKey": "answer"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input-1", "target": "knowledge-1"},
            {"id": "e2", "source": "knowledge-1", "target": "output-1"},
        ],
    }


def failing_tool_workflow(policy: str) -> dict:
    return {
        "name": f"Failing Tool {policy}",
        "version": "0.2.0",
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
                    "toolName": "local.missing",
                    "toolUrl": f"{BASE_URL}/api/missing-endpoint",
                    "toolMethod": "GET",
                    "toolHeaders": "{}",
                    "toolParams": "{}",
                    "failurePolicy": policy,
                    "retryCount": 1,
                    "outputKey": "tool_result",
                },
            },
            {
                "id": "output-1",
                "position": {"x": 520, "y": 0},
                "data": {"kind": "output", "label": "最终回答", "prompt": "{{tool_result}}", "outputKey": "answer"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input-1", "target": "tool-1"},
            {"id": "e2", "source": "tool-1", "target": "output-1"},
        ],
    }


def main() -> None:
    health = request("/api/health")
    knowledge_status = request("/api/knowledge/status")
    initial_knowledge_documents = request("/api/knowledge/documents")
    uploaded_document = request(
        "/api/knowledge/documents",
        "POST",
        {
            "filename": "smoke-test.md",
            "content": "# Smoke Test\n\n烟雾测试文档用于验证知识库上传和删除。",
        },
    )
    knowledge_documents_after_upload = request("/api/knowledge/documents")
    workflow = {
        "name": "Smoke Test Workflow",
        "version": "0.2.0",
        "nodes": [
            {
                "id": "input-1",
                "position": {"x": 600, "y": 0},
                "data": {"kind": "input", "label": "用户输入", "outputKey": "user_request"},
            },
            {
                "id": "llm-1",
                "position": {"x": 300, "y": 0},
                "data": {
                    "kind": "llm",
                    "label": "大模型草稿",
                    "model": "gpt-5.4-mini",
                    "temperature": 0.3,
                    "maxOutputTokens": 800,
                    "timeoutSeconds": 30,
                    "systemPrompt": "你是测试助手。",
                    "prompt": "请回复：{{user_request}}",
                    "outputKey": "draft",
                },
            },
            {
                "id": "output-1",
                "position": {"x": 0, "y": 0},
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
    archived_payload = {**workflow, "archived": True}
    archived_workflow = request(f"/api/workflows/{created['id']}", "PUT", archived_payload)
    fetched_workflow = request(f"/api/workflows/{created['id']}")
    workflows_after_archive = request("/api/workflows")
    run = request("/api/runs", "POST", {"workflow": workflow, "input_text": "测试输入"})
    branch_true_run = request("/api/runs", "POST", {"workflow": branch_workflow(), "input_text": "我要退款"})
    branch_false_run = request("/api/runs", "POST", {"workflow": branch_workflow(), "input_text": "我要咨询"})
    tool_run = request("/api/runs", "POST", {"workflow": http_tool_workflow(), "input_text": "检查后端"})
    knowledge_run = request("/api/runs", "POST", {"workflow": knowledge_workflow(), "input_text": "退款多久到账"})
    skip_failed_run = request("/api/runs", "POST", {"workflow": failing_tool_workflow("skip_downstream"), "input_text": "失败"})
    stop_failed_run = request("/api/runs", "POST", {"workflow": failing_tool_workflow("stop"), "input_text": "失败"})
    stored_run = request(f"/api/workflows/{created['id']}/runs", "POST", {"input_text": "后端历史测试"})
    runs = request("/api/runs")
    workflow_runs = request(f"/api/runs?workflow_id={created['id']}")
    fetched_run = request(f"/api/runs/{stored_run['id']}")
    delete_single_result = request(f"/api/runs/{stored_run['id']}", "DELETE")
    delete_knowledge_result = request("/api/knowledge/documents/smoke-test.md", "DELETE")
    deleted_single_status, _ = request_error(f"/api/runs/{stored_run['id']}")
    second_stored_run = request(f"/api/workflows/{created['id']}/runs", "POST", {"input_text": "清理历史测试"})
    delete_workflow_runs_result = request(f"/api/runs?workflow_id={created['id']}", "DELETE")
    workflow_runs_after_clear = request(f"/api/runs?workflow_id={created['id']}")
    third_stored_run = request(f"/api/workflows/{created['id']}/runs", "POST", {"input_text": "删除工作流清理历史测试"})
    delete_workflow_result = request(f"/api/workflows/{created['id']}", "DELETE")
    deleted_workflow_status, _ = request_error(f"/api/workflows/{created['id']}")
    workflow_runs_after_workflow_delete = request(f"/api/runs?workflow_id={created['id']}")

    assert validation["valid"] is True
    assert invalid_validation["valid"] is False
    assert invalid_create_status == 400
    assert invalid_create_body["detail"]["valid"] is False
    assert invalid_run_status == 400
    assert invalid_run_body["detail"]["valid"] is False
    assert created["archived"] is False
    assert archived_workflow["archived"] is True
    assert fetched_workflow["archived"] is True
    assert any(item["id"] == created["id"] and item["archived"] is True for item in workflows_after_archive)
    assert [step["node_id"] for step in run["steps"]] == ["input-1", "llm-1", "output-1"]
    assert next(step for step in branch_true_run["steps"] if step["node_id"] == "true-output")["status"] == "done"
    assert next(step for step in branch_true_run["steps"] if step["node_id"] == "false-output")["status"] == "skipped"
    assert next(step for step in branch_false_run["steps"] if step["node_id"] == "true-output")["status"] == "skipped"
    assert next(step for step in branch_false_run["steps"] if step["node_id"] == "false-output")["status"] == "done"
    tool_step = next(step for step in tool_run["steps"] if step["node_id"] == "tool-1")
    assert tool_step["provider"] == "HTTP 工具"
    assert "HTTP 200" in tool_step["output"]
    assert '"status":"ok"' in tool_step["output"].replace(" ", "")
    knowledge_step = next(step for step in knowledge_run["steps"] if step["node_id"] == "knowledge-1")
    assert knowledge_status["document_count"] >= 1
    assert knowledge_step["provider"] == "本地知识库"
    assert "退款" in knowledge_step["output"]
    assert isinstance(initial_knowledge_documents, list)
    assert uploaded_document["name"] == "smoke-test.md"
    assert any(document["name"] == "smoke-test.md" for document in knowledge_documents_after_upload)
    failed_tool_step = next(step for step in skip_failed_run["steps"] if step["node_id"] == "tool-1")
    skipped_output_step = next(step for step in skip_failed_run["steps"] if step["node_id"] == "output-1")
    assert skip_failed_run["status"] == "ok"
    assert failed_tool_step["status"] == "error"
    assert "共尝试 2 次" in failed_tool_step["input"]
    assert skipped_output_step["status"] == "skipped"
    assert stop_failed_run["status"] == "error"
    assert [step["node_id"] for step in stop_failed_run["steps"]] == ["input-1", "tool-1"]
    assert any(
        step.get("provider") == "模拟输出"
        or str(step.get("provider", "")).startswith("OpenAI")
        or str(step.get("provider", "")).startswith("DeepSeek")
        for step in run["steps"]
    )
    llm_step = next(step for step in run["steps"] if step.get("provider"))
    assert "error" in llm_step or llm_step.get("provider") != "模拟输出"
    assert "temperature=0.3" in llm_step["input"]
    assert "max_output_tokens=800" in llm_step["input"]
    assert "timeout=30s" in llm_step["input"]
    assert len(workflow_runs) >= 1
    assert all(run["workflow_id"] == created["id"] for run in workflow_runs)
    assert delete_single_result == {}
    assert delete_knowledge_result == {}
    assert deleted_single_status == 404
    assert second_stored_run["workflow_id"] == created["id"]
    assert delete_workflow_runs_result == {}
    assert workflow_runs_after_clear == []
    assert third_stored_run["workflow_id"] == created["id"]
    assert delete_workflow_result == {}
    assert deleted_workflow_status == 404
    assert workflow_runs_after_workflow_delete == []

    print(
        json.dumps(
            {
                "health": health,
                "validation_valid": validation["valid"],
                "invalid_validation_valid": invalid_validation["valid"],
                "invalid_create_status": invalid_create_status,
                "invalid_run_status": invalid_run_status,
                "created_id": created["id"],
                "archived_workflow": archived_workflow["archived"],
                "run_status": run["status"],
                "step_count": len(run["steps"]),
                "llm_provider": llm_step.get("provider"),
                "llm_error": llm_step.get("error"),
                "branch_true_status": [step["status"] for step in branch_true_run["steps"]],
                "branch_false_status": [step["status"] for step in branch_false_run["steps"]],
                "tool_provider": tool_step.get("provider"),
                "knowledge_documents": knowledge_status["document_count"],
                "knowledge_provider": knowledge_step.get("provider"),
                "uploaded_knowledge_document": uploaded_document["name"],
                "skip_failed_status": [step["status"] for step in skip_failed_run["steps"]],
                "stop_failed_status": stop_failed_run["status"],
                "stored_run_id": stored_run["id"],
                "run_count": len(runs),
                "workflow_run_count": len(workflow_runs),
                "deleted_single_status": deleted_single_status,
                "workflow_runs_after_clear": len(workflow_runs_after_clear),
                "deleted_workflow_status": deleted_workflow_status,
                "workflow_runs_after_workflow_delete": len(workflow_runs_after_workflow_delete),
                "fetched_run_status": fetched_run["status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
