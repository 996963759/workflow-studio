import os
from typing import Any

from openai import OpenAI, OpenAIError

from .models import RunResponse, RunStep, WorkflowPayload

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"


def render_template(template: str | None, context: dict[str, str]) -> str:
    value = template or ""
    for key, replacement in context.items():
        value = value.replace(f"{{{{{key}}}}}", replacement)
        value = value.replace(f"{{{{ {key} }}}}", replacement)
    return value


def node_label(node: dict[str, Any]) -> str:
    return str(node.get("data", {}).get("label") or node.get("id") or "未命名节点")


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


def select_deepseek_model(configured_model: Any) -> str:
    model = str(configured_model or "").strip()
    if model.startswith("deepseek-"):
        return model
    return os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL


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
    nodes = sorted(workflow.nodes, key=lambda node: node.get("position", {}).get("x", 0))
    steps: list[RunStep] = []

    for index, node in enumerate(nodes, start=1):
        data = node.get("data", {})
        kind = data.get("kind")
        output_key = data.get("outputKey")
        title = f"{index}. {node_label(node)}"
        provider = None
        error = None

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
            params = render_template(data.get("toolParams"), context)
            output = f"{data.get('toolName') or '未命名工具'} 返回模拟结果。"
            step_input = params or "未配置请求参数"
        elif kind == "condition":
            variable = data.get("conditionVariable") or ""
            operator = data.get("conditionOperator") or "contains"
            target = render_template(data.get("conditionValue"), context)
            value = context.get(variable, "")
            passed = bool(value) if operator == "not_empty" else (value == target if operator == "equals" else target in value)
            output = "条件通过，继续执行。" if passed else "条件未通过，当前后端模拟仍继续生成后续步骤。"
            step_input = f"{{{{{variable}}}}} {operator} {target}".strip()
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
