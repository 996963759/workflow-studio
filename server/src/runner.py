import os
import json
from collections import defaultdict, deque
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from openai import OpenAI, OpenAIError

from .models import RunResponse, RunStep, WorkflowPayload

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
ALLOWED_TOOL_HOSTS = {"127.0.0.1", "localhost", "::1"}
TOOL_TIMEOUT_SECONDS = 10


def render_template(template: str | None, context: dict[str, str]) -> str:
    value = template or ""
    for key, replacement in context.items():
        value = value.replace(f"{{{{{key}}}}}", replacement)
        value = value.replace(f"{{{{ {key} }}}}", replacement)
    return value


def node_label(node: dict[str, Any]) -> str:
    return str(node.get("data", {}).get("label") or node.get("id") or "未命名节点")


def node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or "")


def create_execution_order(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    node_by_id = {node_id(node): node for node in nodes}
    indegree = {item: 0 for item in node_by_id}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_by_id or target not in node_by_id:
            continue
        indegree[target] += 1
        outgoing[source].append(target)

    queue = deque(
        sorted(
            [item for item, degree in indegree.items() if degree == 0],
            key=lambda item: node_by_id[item].get("position", {}).get("x", 0),
        )
    )
    ordered_ids: list[str] = []

    while queue:
        current = queue.popleft()
        ordered_ids.append(current)
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    if len(ordered_ids) != len(node_by_id):
        return None
    return [node_by_id[item] for item in ordered_ids]


def get_reachable_node_ids(start_ids: list[str], edges: list[dict[str, Any]]) -> set[str]:
    reachable: set[str] = set()
    queue = deque(start_ids)

    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        for edge in edges:
            if str(edge.get("source") or "") != current:
                continue
            target = str(edge.get("target") or "")
            if target and target not in reachable:
                queue.append(target)

    return reachable


def get_provider_status() -> dict[str, str | bool]:
    return {
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        "deepseek_model": os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL,
        "deepseek_base_url": os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "openai_default_model": DEFAULT_OPENAI_MODEL,
    }


def create_openai_client(api_key_env: str, base_url: str | None = None) -> OpenAI | None:
    api_key = os.getenv(api_key_env)
    if not api_key:
        return None
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    return str(response)


def summarize_error(error: Exception) -> str:
    message = str(error).strip().replace("\n", " ")
    if len(message) > 220:
        message = f"{message[:217]}..."
    return f"{error.__class__.__name__}: {message}" if message else error.__class__.__name__


def parse_json_object(value: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not value.strip():
        return fallback or {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("JSON value must be an object")
    return parsed


def is_allowed_tool_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in ALLOWED_TOOL_HOSTS


def run_http_tool_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str, str | None]:
    tool_url = render_template(data.get("toolUrl"), context).strip()
    method = str(data.get("toolMethod") or "GET").upper()
    headers_text = render_template(data.get("toolHeaders"), context)
    body_text = render_template(data.get("toolParams"), context)

    if not tool_url:
        tool_name = data.get("toolName") or "未命名工具"
        return f"{tool_name} 返回模拟结果。", body_text or "未配置请求体", None

    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError(f"Unsupported HTTP method: {method}")

    if not is_allowed_tool_url(tool_url):
        raise ValueError("Tool URL is blocked. Only localhost and 127.0.0.1 are allowed by default.")

    headers = {str(key): str(value) for key, value in parse_json_object(headers_text).items()}
    data_bytes = None
    if method not in {"GET", "DELETE"} and body_text.strip():
        parse_json_object(body_text)
        data_bytes = body_text.encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    request = Request(tool_url, data=data_bytes, headers=headers, method=method)
    step_input = "\n".join(
        [
            f"{method} {tool_url}",
            f"Headers: {json.dumps(headers, ensure_ascii=False)}",
            f"Body: {body_text.strip() or '(empty)'}",
        ]
    )

    try:
        with urlopen(request, timeout=TOOL_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            output = f"HTTP {response.status} {response.reason}\n{response_body}"
            return output.strip(), step_input, None
    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        output = f"HTTP {error.code} {error.reason}\n{response_body}"
        return output.strip(), step_input, summarize_error(error)
    except URLError as error:
        raise RuntimeError(str(error.reason)) from error


def select_deepseek_model(configured_model: Any) -> str:
    model = str(configured_model or "").strip()
    if model.startswith("deepseek-"):
        return model
    return os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL


def evaluate_condition(data: dict[str, Any], context: dict[str, str]) -> tuple[bool, str]:
    variable = str(data.get("conditionVariable") or "")
    operator = str(data.get("conditionOperator") or "contains")
    target = render_template(data.get("conditionValue"), context).strip()
    value = context.get(variable, "")

    if operator == "not_empty":
        return bool(value.strip()), f"判断 {{{{{variable or '未选择变量'}}}}} 是否不为空。"

    if operator == "equals":
        return value == target, f"判断 {{{{{variable or '未选择变量'}}}}} 是否等于 \"{target}\"。"

    return (target in value if target else True), f"判断 {{{{{variable or '未选择变量'}}}}} 是否包含 \"{target}\"。"


def run_deepseek_node(data: dict[str, Any], system_prompt: str, prompt: str) -> tuple[str, str]:
    model = select_deepseek_model(data.get("model"))
    client = create_openai_client(
        "DEEPSEEK_API_KEY",
        os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL,
    )
    if not client:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt or "请根据当前工作流上下文生成回复。"})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
    )
    output = response.choices[0].message.content if response.choices else ""
    return output or "DeepSeek 没有返回文本内容。", model


def run_openai_node(data: dict[str, Any], system_prompt: str, prompt: str) -> tuple[str, str]:
    model = str(data.get("model") or DEFAULT_OPENAI_MODEL)
    client = create_openai_client("OPENAI_API_KEY")
    if not client:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    response = client.responses.create(
        model=model,
        instructions=system_prompt or None,
        input=prompt or "请根据当前工作流上下文生成回复。",
    )
    output = extract_response_text(response).strip()
    return output or "OpenAI 没有返回文本内容。", model


def run_llm_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str, str | None, str | None]:
    system_prompt = render_template(data.get("systemPrompt"), context)
    prompt = render_template(data.get("prompt"), context)
    step_input = "\n\n".join(part for part in [system_prompt, prompt] if part) or "未配置提示词"

    if os.getenv("DEEPSEEK_API_KEY"):
        try:
            output, model = run_deepseek_node(data, system_prompt, prompt)
            return output, step_input, f"DeepSeek - {model}", None
        except (OpenAIError, RuntimeError) as error:
            model = select_deepseek_model(data.get("model"))
            reason = summarize_error(error)
            output = f"DeepSeek {model} 调用失败，已回退模拟草稿：{prompt[:120]}"
            return output, step_input, "模拟输出", reason

    if os.getenv("OPENAI_API_KEY"):
        try:
            output, model = run_openai_node(data, system_prompt, prompt)
            return output, step_input, f"OpenAI - {model}", None
        except (OpenAIError, RuntimeError) as error:
            model = str(data.get("model") or DEFAULT_OPENAI_MODEL)
            reason = summarize_error(error)
            output = f"OpenAI {model} 调用失败，已回退模拟草稿：{prompt[:120]}"
            return output, step_input, "模拟输出", reason

    model = str(data.get("model") or DEFAULT_OPENAI_MODEL)
    output = f"模型 {model} 生成模拟草稿：{prompt[:120]}"
    return output, step_input, "模拟输出", None


def simulate_run(workflow: WorkflowPayload, input_text: str) -> RunResponse:
    context: dict[str, str] = {}
    nodes = create_execution_order(workflow.nodes, workflow.edges)
    if nodes is None:
        return RunResponse(
            status="error",
            steps=[
                RunStep(
                    node_id="workflow-order-error",
                    title="执行顺序计算失败",
                    status="error",
                    input="当前工作流连线",
                    output="工作流存在环形依赖或无效结构，后端无法计算执行顺序。",
                    error="无法根据连线计算拓扑执行顺序。",
                )
            ],
    )
    steps: list[RunStep] = []
    skipped_by_branch: set[str] = set()

    for index, node in enumerate(nodes, start=1):
        current_id = node_id(node)
        data = node.get("data", {})
        kind = data.get("kind")
        output_key = data.get("outputKey")
        title = f"{index}. {node_label(node)}"
        provider = None
        error = None

        if current_id in skipped_by_branch:
            steps.append(
                RunStep(
                    node_id=current_id or f"node-{index}",
                    title=title,
                    status="skipped",
                    input="条件分支未命中该路径。",
                    output="已跳过该分支节点。",
                )
            )
            continue

        if kind == "input":
            output = input_text or data.get("sampleInput") or ""
            step_input = "用户请求"
        elif kind == "knowledge":
            query = render_template(data.get("query"), context)
            top_k = data.get("topK") or 4
            output = f"围绕「{query or input_text}」检索到 {top_k} 段相关内容。"
            step_input = query or "未配置检索语句"
        elif kind == "llm":
            output, step_input, provider, error = run_llm_node(data, context)
        elif kind == "tool":
            try:
                output, step_input, error = run_http_tool_node(data, context)
                provider = "HTTP 工具" if data.get("toolUrl") else "模拟输出"
            except (ValueError, RuntimeError, TimeoutError) as run_error:
                rendered_body = render_template(data.get("toolParams"), context)
                output = f"{data.get('toolName') or '未命名工具'} 调用失败。"
                step_input = rendered_body or "未配置请求体"
                provider = "HTTP 工具"
                error = summarize_error(run_error)
        elif kind == "condition":
            passed, detail = evaluate_condition(data, context)
            branch_edges = [
                edge
                for edge in workflow.edges
                if str(edge.get("source") or "") == current_id and edge.get("sourceHandle") in {"true", "false"}
            ]
            if branch_edges:
                inactive_handle = "false" if passed else "true"
                inactive_targets = [
                    str(edge.get("target") or "")
                    for edge in branch_edges
                    if edge.get("sourceHandle") == inactive_handle
                ]
                skipped_by_branch.update(get_reachable_node_ids(inactive_targets, workflow.edges))
                output = f"{detail} 已进入{'真' if passed else '假'}分支。"
            else:
                output = "条件通过，继续执行。" if passed else "条件未通过，当前后端模拟仍继续生成后续步骤。"
            step_input = detail
        else:
            template = data.get("prompt")
            output = render_template(template, context) or "没有可输出内容。"
            step_input = template or "未配置输出模板"

        variable = f"{{{{{output_key}}}}}" if output_key else None
        if output_key:
            context[str(output_key)] = output

        steps.append(
            RunStep(
                node_id=str(node.get("id") or f"node-{index}"),
                title=title,
                status="done",
                input=step_input,
                output=output,
                variable=variable,
                provider=provider,
                error=error,
            )
        )

    return RunResponse(status="ok", steps=steps)
