from typing import Any

from .models import RunResponse, RunStep, WorkflowPayload


def render_template(template: str | None, context: dict[str, str]) -> str:
    value = template or ""
    for key, replacement in context.items():
        value = value.replace(f"{{{{{key}}}}}", replacement)
        value = value.replace(f"{{{{ {key} }}}}", replacement)
    return value


def node_label(node: dict[str, Any]) -> str:
    return str(node.get("data", {}).get("label") or node.get("id") or "未命名节点")


def simulate_run(workflow: WorkflowPayload, input_text: str) -> RunResponse:
    context: dict[str, str] = {}
    nodes = sorted(workflow.nodes, key=lambda node: node.get("position", {}).get("x", 0))
    steps: list[RunStep] = []

    for index, node in enumerate(nodes, start=1):
        data = node.get("data", {})
        kind = data.get("kind")
        output_key = data.get("outputKey")
        title = f"{index}. {node_label(node)}"

        if kind == "input":
            output = input_text or data.get("sampleInput") or ""
            step_input = "用户请求"
        elif kind == "knowledge":
            query = render_template(data.get("query"), context)
            top_k = data.get("topK") or 4
            output = f"围绕「{query or input_text}」检索到 {top_k} 段相关内容。"
            step_input = query or "未配置检索语句"
        elif kind == "llm":
            system_prompt = render_template(data.get("systemPrompt"), context)
            prompt = render_template(data.get("prompt"), context)
            output = f"模型 {data.get('model') or '未指定'} 生成模拟草稿：{prompt[:120]}"
            step_input = "\n\n".join(part for part in [system_prompt, prompt] if part) or "未配置提示词"
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
            )
        )

    return RunResponse(status="ok", steps=steps)
