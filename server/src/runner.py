import os
from typing import Any

from openai import OpenAI, OpenAIError

from .models import RunResponse, RunStep, WorkflowPayload


def render_template(template: str | None, context: dict[str, str]) -> str:
    value = template or ""
    for key, replacement in context.items():
        value = value.replace(f"{{{{{key}}}}}", replacement)
        value = value.replace(f"{{{{ {key} }}}}", replacement)
    return value


def node_label(node: dict[str, Any]) -> str:
    return str(node.get("data", {}).get("label") or node.get("id") or "未命名节点")


def create_openai_client() -> OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return OpenAI()


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    return str(response)


def run_llm_node(data: dict[str, Any], context: dict[str, str]) -> tuple[str, str, str | None]:
    system_prompt = render_template(data.get("systemPrompt"), context)
    prompt = render_template(data.get("prompt"), context)
    step_input = "\n\n".join(part for part in [system_prompt, prompt] if part) or "未配置提示词"
    model = str(data.get("model") or "gpt-5.4-mini")
    client = create_openai_client()

    if not client:
        output = f"模型 {model} 生成模拟草稿：{prompt[:120]}"
        return output, step_input, "模拟输出"

    try:
        response = client.responses.create(
            model=model,
            instructions=system_prompt or None,
            input=prompt or "请根据当前工作流上下文生成回复。",
        )
        output = extract_response_text(response).strip()
        return output or "模型没有返回文本内容。", step_input, "OpenAI"
    except OpenAIError as error:
        output = f"模型 {model} 调用失败，已回退模拟草稿：{prompt[:120]}（{error.__class__.__name__}）"
        return output, step_input, "模拟输出"


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

        if kind == "input":
            output = input_text or data.get("sampleInput") or ""
            step_input = "用户请求"
        elif kind == "knowledge":
            query = render_template(data.get("query"), context)
            top_k = data.get("topK") or 4
            output = f"围绕「{query or input_text}」检索到 {top_k} 段相关内容。"
            step_input = query or "未配置检索语句"
        elif kind == "llm":
            output, step_input, provider = run_llm_node(data, context)
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
            )
        )

    return RunResponse(status="ok", steps=steps)
