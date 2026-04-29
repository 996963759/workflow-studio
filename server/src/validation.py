import json
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlparse

from .models import WorkflowIssue, WorkflowPayload, WorkflowValidationResult

ALLOWED_TOOL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or "")


def node_data(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    return data if isinstance(data, dict) else {}


def node_label(node: dict[str, Any]) -> str:
    return str(node_data(node).get("label") or node_id(node) or "未命名节点")


def parse_json_object(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    parsed = json.loads(text)
    return isinstance(parsed, dict)


def is_allowed_tool_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and parsed.hostname in ALLOWED_TOOL_HOSTS


def create_execution_order(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str] | None:
    ids = {node_id(node) for node in nodes}
    indegree = {item: 0 for item in ids}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in ids or target not in ids:
            continue
        indegree[target] += 1
        outgoing[source].append(target)

    queue = deque([item for item, degree in indegree.items() if degree == 0])
    order: list[str] = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    return order if len(order) == len(ids) else None


def validate_workflow(payload: WorkflowPayload) -> WorkflowValidationResult:
    errors: list[WorkflowIssue] = []
    warnings: list[WorkflowIssue] = []
    nodes = payload.nodes
    edges = payload.edges
    ids = {node_id(node) for node in nodes}
    incoming = {item: 0 for item in ids}
    outgoing = {item: 0 for item in ids}

    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in ids or target not in ids:
            continue
        incoming[target] += 1
        outgoing[source] += 1

    if not any(node_data(node).get("kind") == "input" for node in nodes):
        errors.append(WorkflowIssue(id="missing-input", level="error", message="至少需要一个用户输入节点。"))

    if not any(node_data(node).get("kind") == "output" for node in nodes):
        errors.append(WorkflowIssue(id="missing-output", level="error", message="至少需要一个最终回答节点。"))

    if create_execution_order(nodes, edges) is None:
        errors.append(WorkflowIssue(id="cycle", level="error", message="工作流存在环形依赖，无法按顺序执行。"))

    for node in nodes:
        current_id = node_id(node)
        data = node_data(node)
        has_incoming = incoming.get(current_id, 0) > 0
        has_outgoing = outgoing.get(current_id, 0) > 0

        if not has_incoming and not has_outgoing and len(nodes) > 1:
            warnings.append(
                WorkflowIssue(
                    id=f"isolated-{current_id}",
                    level="warning",
                    node_id=current_id,
                    message=f"节点「{node_label(node)}」没有任何连线。",
                )
            )

        if data.get("kind") != "input" and not has_incoming:
            warnings.append(
                WorkflowIssue(
                    id=f"missing-upstream-{current_id}",
                    level="warning",
                    node_id=current_id,
                    message=f"节点「{node_label(node)}」没有上游输入。",
                )
            )

        if data.get("kind") == "output" and not has_incoming:
            errors.append(
                WorkflowIssue(
                    id=f"output-no-upstream-{current_id}",
                    level="error",
                    node_id=current_id,
                    message=f"最终回答节点「{node_label(node)}」必须连接上游节点。",
                )
            )

        if data.get("kind") == "tool":
            tool_url = str(data.get("toolUrl") or "").strip()
            method = str(data.get("toolMethod") or "GET").upper()

            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                errors.append(
                    WorkflowIssue(
                        id=f"tool-method-{current_id}",
                        level="error",
                        node_id=current_id,
                        message=f"工具节点「{node_label(node)}」的请求方法不支持。",
                    )
                )

            if tool_url and not is_allowed_tool_url(tool_url):
                errors.append(
                    WorkflowIssue(
                        id=f"tool-url-{current_id}",
                        level="error",
                        node_id=current_id,
                        message=f"工具节点「{node_label(node)}」只允许请求 localhost、127.0.0.1 或 ::1。",
                    )
                )

            for field, label in [("toolHeaders", "请求头"), ("toolParams", "请求体")]:
                try:
                    if not parse_json_object(data.get(field)):
                        raise ValueError("JSON must be an object")
                except (json.JSONDecodeError, ValueError):
                    errors.append(
                        WorkflowIssue(
                            id=f"{field}-{current_id}",
                            level="error",
                            node_id=current_id,
                            message=f"工具节点「{node_label(node)}」的{label}必须是合法 JSON 对象。",
                        )
                    )

    owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        output_key = str(node_data(node).get("outputKey") or "").strip()
        if output_key:
            owners[output_key].append(node)

    for key, owner_nodes in owners.items():
        if len(owner_nodes) < 2:
            continue
        for node in owner_nodes:
            current_id = node_id(node)
            errors.append(
                WorkflowIssue(
                    id=f"duplicate-var-{key}-{current_id}",
                    level="error",
                    node_id=current_id,
                    message=f"输出变量「{key}」被多个节点重复使用。",
                )
            )

    return WorkflowValidationResult(errors=errors, warnings=warnings, valid=len(errors) == 0)
