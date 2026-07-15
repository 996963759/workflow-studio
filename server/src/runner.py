import os
import json
import re
import time
from collections import defaultdict, deque
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from openai import OpenAI, OpenAIError

from .external_rag import search_paismart
from .knowledge import search_knowledge
from .mcp_tools import call_mcp_tool, format_mcp_result, is_mcp_tool_name
from .models import RunResponse, RunStep, WorkflowPayload
from .providers.aliyun import (
    AliyunProviderError,
    aliyun_configured,
    run_image_generation,
    run_tts,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
ALLOWED_TOOL_HOSTS = {"127.0.0.1", "localhost", "::1", "api"}
TOOL_TIMEOUT_SECONDS = 10
DEFAULT_TEMPERATURE = 0.4
DEFAULT_MAX_OUTPUT_TOKENS = 1200
DEFAULT_LLM_TIMEOUT_SECONDS = 45
FAILURE_POLICIES = {"stop", "continue", "skip_downstream"}


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
        "aliyun_configured": aliyun_configured(),
        "aliyun_tts_model": os.getenv("ALIYUN_TTS_MODEL", "cosyvoice-v2"),
        "aliyun_image_model": os.getenv("ALIYUN_IMAGE_MODEL", "wanx2.1-t2i-turbo"),
    }


def create_openai_client(api_key_env: str, base_url: str | None = None, api_key: str | None = None) -> OpenAI | None:
    api_key = api_key or os.getenv(api_key_env)
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


def elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def clamp_number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number < minimum:
        return minimum
    if number > maximum:
        return maximum
    return number


def llm_options(data: dict[str, Any]) -> tuple[float, int, float]:
    temperature = clamp_number(data.get("temperature"), DEFAULT_TEMPERATURE, 0, 2)
    max_output_tokens = int(clamp_number(data.get("maxOutputTokens"), DEFAULT_MAX_OUTPUT_TOKENS, 1, 32000))
    timeout_seconds = clamp_number(data.get("timeoutSeconds"), DEFAULT_LLM_TIMEOUT_SECONDS, 5, 300)
    return temperature, max_output_tokens, timeout_seconds


def format_llm_options(data: dict[str, Any]) -> str:
    temperature, max_output_tokens, timeout_seconds = llm_options(data)
    return f"参数：temperature={temperature:g}, max_output_tokens={max_output_tokens}, timeout={timeout_seconds:g}s"


def compact_text(value: str, limit: int = 42) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else f"{text[:limit]}..."


def json_llm_fallback(prompt: str, context: dict[str, str]) -> str | None:
    if "智能楼宇设备识别" in prompt:
        return "\n".join(
            [
                "识别结果：",
                "- 楼栋：A 座",
                "- 楼层：18F",
                "- 设备编号：AHU-18F-07",
                "- 异常类型：设备离线、CO2 偏高",
                "- 建议调用 MCP 工具：mcp.building_bms.get_device_status",
                '- 查询参数：{"device_id":"AHU-18F-07","building":"A座","floor":"18F"}',
            ]
        )
    if "简版智能楼宇诊断" in prompt:
        device_sn = context.get("device_sn") or "AHU-18F-07"
        return (
            f"诊断结论：{device_sn} 是 A 座 18F 会议区的新风机组控制器，当前已离线约 30 分钟，同时 CO2 偏高，建议按 P1 处理。\n\n"
            "可能原因：BMS 网关或 BACnet 通讯链路异常，也可能是弱电间交换机端口、控制器供电或网线松动导致。\n\n"
            "建议动作：1. 远程检查 BMS 网关在线状态；2. 现场检查控制器供电和交换机端口；"
            "3. 通讯恢复前安排物业巡检会议区空气质量，并派单给楼宇自控运维二组。"
        )
    if all(
        field in prompt
        for field in ["diagnosis_summary", "root_cause", "risk_level", "work_order_required", "recommended_actions"]
    ):
        device_sn = context.get("device_sn") or context.get("device_id") or "UNKNOWN"
        offline_minutes = context.get("offline_minutes") or "0"
        alarm_level = context.get("alarm_level") or "P2"
        co2_ppm = context.get("co2_ppm") or "未知"
        return json.dumps(
            {
                "diagnosis_summary": f"智能楼宇设备 {device_sn} 当前离线 {offline_minutes} 分钟，会议区 CO2={co2_ppm}ppm，告警等级 {alarm_level}，需要优先处置。",
                "root_cause": "BMS 网关心跳超时并伴随 BACnet 通讯抖动，优先怀疑楼层弱电间交换机端口、控制器供电或网关链路异常。",
                "risk_level": alarm_level,
                "work_order_required": True,
                "recommended_actions": [
                    "远程检查 BMS-GW-A-18F-02 网关在线状态和 BACnet 轮询日志。",
                    "现场核验 A 座 18F 弱电间交换机 Gi1/0/18 端口、控制器供电和网线连接。",
                    "在恢复通讯前将会议区新风阀位切到安全开度，并安排物业巡检 CO2 和温度体感。",
                ],
            },
            ensure_ascii=False,
        )
    if not all(field in prompt for field in ["title", "script", "image_prompt", "caption"]):
        return None
    request = (
        context.get("campaign_request")
        or context.get("voice_request")
        or context.get("user_request")
        or compact_text(prompt, 80)
    )
    subject = compact_text(request, 36)
    return json.dumps(
        {
            "title": f"{subject}短视频素材方案",
            "script": f"这是一段围绕{request}的短视频口播，突出核心卖点、目标受众和使用场景，语气自然，结尾引导用户了解、预约或下单。",
            "image_prompt": f"中文商品营销封面配图，主题是{request}，画面干净专业，突出产品、目标受众、核心卖点和可读标题，适合短视频封面。",
            "caption": f"{request} 发布文案：把亮点讲清楚，把场景拍真实，适合发布到短视频平台。",
            "publish_checklist": ["检查口播节奏", "确认图片不含违规元素", "发布前补充商品链接或预约入口"],
        },
        ensure_ascii=False,
    )


def retry_count(data: dict[str, Any]) -> int:
    try:
        value = int(data.get("retryCount") or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(value, 5))


def failure_policy(data: dict[str, Any]) -> str:
    policy = str(data.get("failurePolicy") or "stop")
    return policy if policy in FAILURE_POLICIES else "stop"


def run_with_retries(action: Any, attempts: int) -> tuple[Any, int, Exception | None]:
    last_error: Exception | None = None
    for attempt in range(attempts + 1):
        try:
            return action(), attempt + 1, None
        except Exception as error:  # noqa: BLE001 - errors are converted into workflow run state.
            last_error = error
    return None, attempts + 1, last_error


def parse_json_object(value: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not value.strip():
        return fallback or {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("JSON value must be an object")
    return parsed


def format_workflow_value(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def parse_json_path_value(source: str, path: str) -> Any:
    parsed = json.loads(source)
    normalized_path = path.strip()
    if not normalized_path:
        return parsed
    current: Any = parsed
    for part in normalized_path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def run_code_expression(expression: str, context: dict[str, str]) -> str:
    helpers = {
        "upper": lambda value: value.upper(),
        "lower": lambda value: value.lower(),
        "trim": lambda value: value.strip(),
        "length": lambda value: str(len(value)),
    }
    text = expression.strip()
    if text.endswith(")") and "(" in text:
        name, argument = text[:-1].split("(", 1)
        if name in helpers:
            return helpers[name](context.get(argument.strip(), ""))
        raise ValueError(f"Unsupported expression function: {name}")
    return render_template(expression, context)


def parse_loop_items(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [format_workflow_value(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in text.replace(",", "\n").splitlines() if item.strip()]


def run_assign_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    template = str(data.get("assignmentValue") or "")
    return render_template(template, context), template or "未配置赋值内容"


def run_template_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    template = str(data.get("templateText") or "")
    return render_template(template, context), template or "未配置模板"


def run_json_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    source = render_template(data.get("jsonSource"), context)
    path = str(data.get("jsonPath") or "")
    value = parse_json_path_value(source, path)
    return format_workflow_value(value), f"路径：{path or '(整个 JSON)'}\n{source}"


def run_code_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    expression = str(data.get("codeExpression") or "")
    return run_code_expression(expression, context), expression or "未配置表达式"


def run_loop_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    rendered_items = render_template(data.get("loopItems"), context)
    items = parse_loop_items(rendered_items)
    template = str(data.get("loopTemplate") or "{{item}}")
    separator = str(data.get("loopSeparator") if data.get("loopSeparator") is not None else "\n")
    output = separator.join(
        render_template(template, {**context, "item": item, "index": str(index)})
        for index, item in enumerate(items, start=1)
    )
    return output or "没有可迭代内容。", rendered_items or "未配置列表来源"


def run_aggregate_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    names = [
        item.strip()
        for item in str(data.get("aggregateVariables") or "").replace(",", "\n").splitlines()
        if item.strip()
    ]
    separator = str(data.get("aggregateSeparator") if data.get("aggregateSeparator") is not None else "\n\n")
    output = separator.join(context.get(name, "") for name in names if context.get(name, ""))
    return output or "没有聚合到变量内容。", ", ".join(names) or "未配置聚合变量"


def is_allowed_tool_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in ALLOWED_TOOL_HOSTS


def container_api_fallback_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return None
    if parsed.port not in {8000, None}:
        return None
    netloc = "api:8000" if not parsed.username else ""
    if not netloc:
        return None
    return urlunparse(parsed._replace(netloc=netloc))


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
        raise ValueError("Tool URL is blocked. Only localhost, 127.0.0.1, ::1 and compose service api are allowed by default.")

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
        fallback_url = container_api_fallback_url(tool_url)
        if fallback_url and is_allowed_tool_url(fallback_url):
            fallback_request = Request(fallback_url, data=data_bytes, headers=headers, method=method)
            fallback_step_input = f"{step_input}\n容器内重试：{method} {fallback_url}"
            try:
                with urlopen(fallback_request, timeout=TOOL_TIMEOUT_SECONDS) as response:
                    response_body = response.read().decode("utf-8", errors="replace")
                    output = f"HTTP {response.status} {response.reason}\n{response_body}"
                    return output.strip(), fallback_step_input, None
            except HTTPError as fallback_error:
                response_body = fallback_error.read().decode("utf-8", errors="replace")
                output = f"HTTP {fallback_error.code} {fallback_error.reason}\n{response_body}"
                return output.strip(), fallback_step_input, summarize_error(fallback_error)
            except URLError:
                pass
        raise RuntimeError(str(error.reason)) from error


def run_mcp_tool_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str, str | None]:
    tool_name = str(data.get("toolName") or "").strip()
    body_text = render_template(data.get("toolParams"), context)
    try:
        arguments = parse_json_object(body_text)
    except (json.JSONDecodeError, ValueError):
        if tool_name != "mcp.building_bms.get_device_status":
            raise
        arguments = {
            "device_id": extract_json_string_field(body_text, "device_id") or "AHU-18F-07",
            "building": extract_json_string_field(body_text, "building") or "A座",
            "floor": extract_json_string_field(body_text, "floor") or "18F",
            "source": context.get("device_query", ""),
        }
    result = call_mcp_tool(tool_name, arguments)
    step_input = "\n".join(
        [
            f"Tool: {tool_name}",
            f"Arguments: {json.dumps(arguments, ensure_ascii=False)}",
        ]
    )
    return format_mcp_result(result), step_input, None


def extract_json_string_field(value: str, field: str) -> str | None:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"([^"]*)"', value)
    return match.group(1) if match else None


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


def run_deepseek_node(
    data: dict[str, Any],
    system_prompt: str,
    prompt: str,
    runtime_config: dict[str, str | bool] | None = None,
) -> tuple[str, str]:
    configured_model = runtime_config.get("model") if runtime_config else data.get("model")
    model = select_deepseek_model(configured_model)
    temperature, max_output_tokens, timeout_seconds = llm_options(data)
    client = create_openai_client(
        "DEEPSEEK_API_KEY",
        str(runtime_config.get("base_url") or "") if runtime_config else os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL,
        str(runtime_config.get("api_key") or "") if runtime_config else None,
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
        temperature=temperature,
        max_tokens=max_output_tokens,
        timeout=timeout_seconds,
        stream=False,
    )
    output = response.choices[0].message.content if response.choices else ""
    return output or "DeepSeek 没有返回文本内容。", model


def run_openai_node(data: dict[str, Any], system_prompt: str, prompt: str) -> tuple[str, str]:
    model = str(data.get("model") or DEFAULT_OPENAI_MODEL)
    temperature, max_output_tokens, timeout_seconds = llm_options(data)
    client = create_openai_client("OPENAI_API_KEY")
    if not client:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    response = client.responses.create(
        model=model,
        instructions=system_prompt or None,
        input=prompt or "请根据当前工作流上下文生成回复。",
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        timeout=timeout_seconds,
    )
    output = extract_response_text(response).strip()
    return output or "OpenAI 没有返回文本内容。", model


def run_llm_node(
    data: dict[str, Any],
    context: dict[str, str],
    model_configs: dict[str, dict[str, str | bool]] | None = None,
) -> tuple[str, str, str | None, str | None]:
    system_prompt = render_template(data.get("systemPrompt"), context)
    prompt = render_template(data.get("prompt"), context)
    step_input = "\n\n".join(part for part in [format_llm_options(data), system_prompt, prompt] if part) or "未配置提示词"

    workspace_deepseek = model_configs.get("deepseek") if model_configs else None
    if workspace_deepseek:
        try:
            output, model = run_deepseek_node(data, system_prompt, prompt, workspace_deepseek)
            return output, step_input, f"DeepSeek 工作区配置 - {model}", None
        except (OpenAIError, RuntimeError) as error:
            model = select_deepseek_model(workspace_deepseek.get("model"))
            reason = summarize_error(error)
            output = json_llm_fallback(prompt, context) or f"DeepSeek 工作区配置 {model} 调用失败，已回退模拟草稿：{prompt[:120]}"
            return output, step_input, "模拟输出", reason

    if os.getenv("DEEPSEEK_API_KEY"):
        try:
            output, model = run_deepseek_node(data, system_prompt, prompt)
            return output, step_input, f"DeepSeek - {model}", None
        except (OpenAIError, RuntimeError) as error:
            model = select_deepseek_model(data.get("model"))
            reason = summarize_error(error)
            output = json_llm_fallback(prompt, context) or f"DeepSeek {model} 调用失败，已回退模拟草稿：{prompt[:120]}"
            return output, step_input, "模拟输出", reason

    if os.getenv("OPENAI_API_KEY"):
        try:
            output, model = run_openai_node(data, system_prompt, prompt)
            return output, step_input, f"OpenAI - {model}", None
        except (OpenAIError, RuntimeError) as error:
            model = str(data.get("model") or DEFAULT_OPENAI_MODEL)
            reason = summarize_error(error)
            output = json_llm_fallback(prompt, context) or f"OpenAI {model} 调用失败，已回退模拟草稿：{prompt[:120]}"
            return output, step_input, "模拟输出", reason

    model = str(data.get("model") or DEFAULT_OPENAI_MODEL)
    output = json_llm_fallback(prompt, context) or f"模型 {model} 使用 {format_llm_options(data)} 生成模拟草稿：{prompt[:120]}"
    return output, step_input, "模拟输出", None


def run_knowledge_node(
    data: dict[str, Any],
    context: dict[str, str],
    input_text: str,
    user_id: str | None = None,
    workspace_id: str | None = None,
    model_configs: dict[str, dict[str, str | bool]] | None = None,
) -> tuple[str, str, str | None]:
    query = render_template(data.get("query"), context).strip() or input_text
    top_k = int(data.get("topK") or 4)
    provider_mode = str(data.get("knowledgeProvider") or "local")
    step_input = query or "未配置检索语句"
    provider = "本地知识库"

    if provider_mode == "paismart":
        try:
            matches = search_paismart(query, top_k, model_configs.get("paismart") if model_configs else None)
            provider = "PaiSmart RAG"
        except Exception as error:  # noqa: BLE001 - fallback is shown in the run log.
            matches = search_knowledge(query, top_k, user_id, workspace_id)
            provider = "本地知识库"
            if not matches:
                return (
                    "PaiSmart RAG 调用失败，且本地知识库没有检索到相关片段。",
                    step_input,
                    f"PaiSmart RAG 失败后回退本地知识库：{summarize_error(error)}",
                )
            step_input = f"{step_input}\nPaiSmart RAG 调用失败，已回退本地知识库：{summarize_error(error)}"
    else:
        matches = search_knowledge(query, top_k, user_id, workspace_id)

    if not matches:
        return f"没有在{provider}中检索到相关片段。", step_input, provider

    output = "\n\n".join(
        f"[{index}. {match.source} | score={match.score}]\n{match.text}"
        for index, match in enumerate(matches, start=1)
    )
    return output, step_input, provider


def run_tts_node(
    data: dict[str, Any],
    context: dict[str, str],
    runtime_config: dict[str, str | bool] | None = None,
) -> tuple[str, str, str, str | None]:
    text = render_template(data.get("ttsText") or data.get("prompt"), context).strip()
    model = str(data.get("ttsModel") or (runtime_config or {}).get("model") or os.getenv("ALIYUN_TTS_MODEL") or "cosyvoice-v2")
    voice = str(data.get("ttsVoice") or os.getenv("ALIYUN_TTS_VOICE") or "longxiaochun_v2")
    audio_format = str(data.get("audioFormat") or "mp3")
    speech_rate = clamp_number(data.get("speechRate"), 1.0, 0.5, 2.0)
    step_input = f"文本：{text or '未配置文本'}\n音色：{voice}\n格式：{audio_format}\n语速：{speech_rate:g}"

    if not text:
        return "未配置要合成语音的文本。", step_input, "模拟输出", "TTS 文本为空"
    if not aliyun_configured(runtime_config):
        return f"阿里云 TTS 未配置 Key，模拟生成音频：{text[:80]}", step_input, "模拟输出", None
    try:
        audio_url, used_model = run_tts(text, model, voice, audio_format, speech_rate, runtime_config)
        return f"音频地址：{audio_url}", step_input, f"阿里云 TTS - {used_model}", None
    except AliyunProviderError as error:
        return f"阿里云 TTS 调用失败，已回退模拟音频：{text[:80]}", step_input, "模拟输出", summarize_error(error)


def run_image_node(
    data: dict[str, Any],
    context: dict[str, str],
    runtime_config: dict[str, str | bool] | None = None,
) -> tuple[str, str, str, str | None]:
    prompt = render_template(data.get("imagePrompt") or data.get("prompt"), context).strip()
    model = str(data.get("imageModel") or os.getenv("ALIYUN_IMAGE_MODEL") or "wanx2.1-t2i-turbo")
    size = str(data.get("imageSize") or "1024*1024")
    count = int(clamp_number(data.get("imageCount"), 1, 1, 4))
    step_input = f"提示词：{prompt or '未配置提示词'}\n尺寸：{size}\n数量：{count}"

    if not prompt:
        return "未配置图片生成提示词。", step_input, "模拟输出", "图片提示词为空"
    if not aliyun_configured(runtime_config):
        return f"阿里云图片生成未配置 Key，模拟生成 {count} 张图片：{prompt[:80]}", step_input, "模拟输出", None
    try:
        urls, used_model = run_image_generation(prompt, model, size, count, runtime_config)
        output = "\n".join(f"图片 {index}: {url}" for index, url in enumerate(urls, start=1))
        return output, step_input, f"阿里云图片生成 - {used_model}", None
    except AliyunProviderError as error:
        return f"阿里云图片生成调用失败，已回退模拟图片：{prompt[:80]}", step_input, "模拟输出", summarize_error(error)


def simulate_run(
    workflow: WorkflowPayload,
    input_text: str,
    user_id: str | None = None,
    workspace_id: str | None = None,
    model_configs: dict[str, dict[str, str | bool]] | None = None,
) -> RunResponse:
    run_started_at = time.perf_counter()
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
                    kind="workflow",
                    error="无法根据连线计算拓扑执行顺序。",
                    duration_ms=elapsed_ms(run_started_at),
                )
            ],
    )
    steps: list[RunStep] = []
    skipped_by_branch: set[str] = set()

    for index, node in enumerate(nodes, start=1):
        step_started_at = time.perf_counter()
        current_id = node_id(node)
        data = node.get("data", {})
        kind = data.get("kind")
        output_key = data.get("outputKey")
        title = f"{index}. {node_label(node)}"
        provider = None
        error = None
        status = "done"
        attempts = 1

        if current_id in skipped_by_branch:
            steps.append(
                RunStep(
                    node_id=current_id or f"node-{index}",
                    title=title,
                    status="skipped",
                    input="条件分支未命中该路径。",
                    output="已跳过该分支节点。",
                    kind=str(kind or "unknown"),
                    duration_ms=elapsed_ms(step_started_at),
                )
            )
            continue

        if kind == "input":
            output = input_text or data.get("sampleInput") or ""
            step_input = "用户请求"
        elif kind == "knowledge":
            output, step_input, provider = run_knowledge_node(data, context, input_text, user_id, workspace_id, model_configs)
        elif kind == "assign":
            output, step_input = run_assign_node(data, context)
        elif kind == "template":
            output, step_input = run_template_node(data, context)
        elif kind == "json":
            try:
                output, step_input = run_json_node(data, context)
            except (json.JSONDecodeError, ValueError, TypeError, IndexError) as error:
                output = "JSON 解析失败。"
                step_input = render_template(data.get("jsonSource"), context) or "未配置 JSON 来源"
                error = summarize_error(error)
                status = "error"
        elif kind == "code":
            try:
                output, step_input = run_code_node(data, context)
            except ValueError as run_error:
                output = "代码表达式执行失败。"
                step_input = str(data.get("codeExpression") or "未配置表达式")
                error = summarize_error(run_error)
                status = "error"
        elif kind == "loop":
            output, step_input = run_loop_node(data, context)
        elif kind == "aggregate":
            output, step_input = run_aggregate_node(data, context)
        elif kind == "llm":
            output, step_input, provider, error = run_llm_node(data, context, model_configs)
        elif kind == "tts":
            output, step_input, provider, error = run_tts_node(data, context, model_configs.get("aliyun") if model_configs else None)
        elif kind == "image":
            output, step_input, provider, error = run_image_node(data, context, model_configs.get("aliyun") if model_configs else None)
        elif kind == "tool":
            tool_name = str(data.get("toolName") or "").strip()
            provider = "MCP 工具" if is_mcp_tool_name(tool_name) else ("HTTP 工具" if data.get("toolUrl") else "模拟输出")
            def run_tool_once() -> tuple[str, str, str | None]:
                if is_mcp_tool_name(tool_name):
                    return run_mcp_tool_node(data, context)
                result = run_http_tool_node(data, context)
                if result[2]:
                    raise RuntimeError(result[2])
                return result

            result, attempts, run_error = run_with_retries(run_tool_once, retry_count(data))
            if run_error or result is None:
                rendered_body = render_template(data.get("toolParams"), context)
                output = f"{data.get('toolName') or '未命名工具'} 调用失败。"
                step_input = rendered_body or "未配置请求体"
                error = summarize_error(run_error)
                status = "error"
            else:
                output, step_input, error = result
                if error:
                    status = "error"
            if attempts > 1:
                step_input = f"{step_input}\n重试：共尝试 {attempts} 次。"
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
        if output_key and status != "error":
            context[str(output_key)] = output

        steps.append(
            RunStep(
                node_id=str(node.get("id") or f"node-{index}"),
                title=title,
                status=status,
                input=step_input,
                output=output,
                kind=str(kind or "unknown"),
                variable=variable,
                provider=provider,
                error=error,
                duration_ms=elapsed_ms(step_started_at),
                attempt_count=attempts,
            )
        )

        if status == "error":
            policy = failure_policy(data)
            if policy == "stop":
                return RunResponse(status="error", steps=steps)
            if policy == "skip_downstream":
                skipped_by_branch.update(get_reachable_node_ids([current_id], workflow.edges) - {current_id})

    return RunResponse(status="ok", steps=steps)
