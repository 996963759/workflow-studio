import os

from sqlalchemy import select

from server.src.db import create_session_factory
from server.src.main import workspace_model_configs
from server.src.models import WorkflowPayload
from server.src.orm import DbWorkflow
from server.src.runner import simulate_run
from server.src.storage import WorkflowStore


DEFAULT_USER_ID = "t-uFJp8UzcSpj_ktqdNznw"
DEFAULT_WORKSPACE_ID = "3d9213b0-fea2-4200-b35b-80ff6876c662"
WORKFLOW_NAME = "智能楼宇设备运行状态诊断"
SAMPLE_INPUT = "2号空调-大门右3 最近是不是异常？帮我看一下运行状态、最新数据和告警情况，必要时给出派单建议。"


def workflow_node(node_id: str, kind: str, x: int, y: int, **data: object) -> dict:
    return {
        "id": node_id,
        "type": "workflow",
        "position": {"x": x, "y": y},
        "data": {"kind": kind, **data},
    }


def workflow_payload() -> WorkflowPayload:
    nodes = [
        workflow_node(
            "input-1",
            "input",
            40,
            260,
            label="用户描述设备问题",
            description="客户或内部人员用自然语言描述设备、位置和异常现象。",
            sampleInput=SAMPLE_INPUT,
            outputKey="device_issue",
        ),
        workflow_node(
            "llm-extract",
            "llm",
            360,
            260,
            label="LLM 提取设备与异常",
            description="从用户问题中提取设备别名、位置、系统类型和异常类型。",
            model="deepseek-v4-flash",
            temperature=0,
            maxOutputTokens=600,
            timeoutSeconds=45,
            systemPrompt="你是智能楼宇运维助手的参数规划器。只输出合法 JSON，不要 Markdown，不要解释，不要代码块。",
            prompt=(
                "请从用户描述中提取设备诊断参数，只输出 JSON。\n\n"
                '输出格式：{"device_alias":"设备名称或别名","location":"位置描述","anomaly_type":"异常类型",'
                '"system_type":"Bms","alarm_keyword":"用于告警查询的关键词","intent_summary":"一句话说明用户想诊断什么"}。\n'
                '如果没有明确设备名称，演示默认 device_alias 填 "2号空调-大门右3"；'
                'system_type 只能是 "Bms"、"IoT" 或 "SmallClient"，智能楼宇空调/BMS 默认填 "Bms"；'
                "alarm_keyword 默认等于 device_alias。\n\n"
                "用户描述：{{device_issue}}"
            ),
            outputKey="diagnosis_plan_json",
            failurePolicy="continue",
            retryCount=1,
        ),
        workflow_node(
            "json-device-alias",
            "json",
            720,
            100,
            label="提取设备别名",
            jsonSource="{{diagnosis_plan_json}}",
            jsonPath="device_alias",
            outputKey="device_alias",
        ),
        workflow_node(
            "json-system-type",
            "json",
            720,
            260,
            label="提取系统类型",
            jsonSource="{{diagnosis_plan_json}}",
            jsonPath="system_type",
            outputKey="system_type",
        ),
        workflow_node(
            "json-anomaly",
            "json",
            720,
            420,
            label="提取异常类型",
            jsonSource="{{diagnosis_plan_json}}",
            jsonPath="anomaly_type",
            outputKey="anomaly_type",
        ),
        workflow_node(
            "json-alarm-keyword",
            "json",
            720,
            580,
            label="提取告警关键词",
            jsonSource="{{diagnosis_plan_json}}",
            jsonPath="alarm_keyword",
            outputKey="alarm_keyword",
        ),
        workflow_node(
            "mcp-alias-resolve",
            "tool",
            1080,
            180,
            label="MCP 解析设备/传感器 ID",
            description="调用 iot-mcp.iot_sensor_alias_resolve，把用户可读设备名解析成 sensorId。",
            toolName="iot-mcp.iot_sensor_alias_resolve",
            toolUrl="",
            toolMethod="POST",
            toolHeaders="{}",
            toolParams='{\n  "aliases": ["{{device_alias}}"],\n  "systemType": "{{system_type}}"\n}',
            outputKey="alias_resolve_result",
            failurePolicy="skip_downstream",
            retryCount=1,
        ),
        workflow_node(
            "json-alias-payload",
            "json",
            1420,
            120,
            label="读取解析结果 JSON",
            jsonSource="{{alias_resolve_result}}",
            jsonPath="data.0.text",
            outputKey="alias_payload_json",
        ),
        workflow_node(
            "json-sensor-id",
            "json",
            1740,
            120,
            label="提取 sensorId",
            jsonSource="{{alias_payload_json}}",
            jsonPath="items.0.sensorId",
            outputKey="sensor_id",
        ),
        workflow_node(
            "mcp-latest-data",
            "tool",
            2060,
            120,
            label="MCP 查询最新运行数据",
            description="调用 iot-mcp.iot_sensor_latest_data_query，查询传感器最新状态、温度、模式、风速等数据。",
            toolName="iot-mcp.iot_sensor_latest_data_query",
            toolUrl="",
            toolMethod="POST",
            toolHeaders="{}",
            toolParams='{\n  "sensorIds": ["{{sensor_id}}"],\n  "systemType": "{{system_type}}"\n}',
            outputKey="latest_data_result",
            failurePolicy="continue",
            retryCount=1,
        ),
        workflow_node(
            "json-latest-payload",
            "json",
            2400,
            120,
            label="读取最新数据 JSON",
            jsonSource="{{latest_data_result}}",
            jsonPath="data.0.text",
            outputKey="latest_data_json",
        ),
        workflow_node(
            "mcp-alarm-query",
            "tool",
            1080,
            520,
            label="MCP 查询告警状态",
            description="调用 neuron-messaging-mcp.messaging_alarm_device_query，查询该设备当前告警状态和最近告警。",
            toolName="neuron-messaging-mcp.messaging_alarm_device_query",
            toolUrl="",
            toolMethod="POST",
            toolHeaders="{}",
            toolParams='{\n  "keyword": "{{alarm_keyword}}",\n  "page": 1,\n  "pageSize": 5\n}',
            outputKey="alarm_query_result",
            failurePolicy="continue",
            retryCount=1,
        ),
        workflow_node(
            "json-alarm-payload",
            "json",
            1420,
            520,
            label="读取告警 JSON",
            jsonSource="{{alarm_query_result}}",
            jsonPath="data.0.text",
            outputKey="alarm_data_json",
        ),
        workflow_node(
            "llm-diagnosis",
            "llm",
            2740,
            300,
            label="LLM 汇总诊断结果",
            description="综合设备解析、最新运行数据和告警状态，输出诊断结论与派单建议。",
            model="deepseek-v4-flash",
            temperature=0.2,
            maxOutputTokens=1200,
            timeoutSeconds=60,
            systemPrompt=(
                "你是智能楼宇设备诊断助手。只基于 MCP 返回数据做判断；缺少数据时说明缺口，不要编造。"
                "写操作只能给建议，不能声称已经派单。"
            ),
            prompt=(
                "用户问题：{{device_issue}}\n诊断意图：{{diagnosis_plan_json}}\n\n"
                "设备解析结果：\n{{alias_payload_json}}\n\n"
                "最新运行数据：\n{{latest_data_json}}\n\n"
                "告警查询结果：\n{{alarm_data_json}}\n\n"
                "请输出中文诊断报告，结构包含：\n"
                "1. 识别到的设备和 sensorId；\n"
                "2. 当前运行状态摘要，重点关注在线状态、开关、模式、风速、设定温度、室温和数据时间；\n"
                "3. 告警状态和风险等级；\n"
                "4. 初步原因判断；\n"
                "5. 是否建议派单。若建议派单，只生成派单建议，包括优先级、处理团队、现场检查项，不要说已经创建工单。"
            ),
            outputKey="diagnosis_answer",
            failurePolicy="continue",
            retryCount=1,
        ),
        workflow_node(
            "output-1",
            "output",
            3120,
            300,
            label="设备诊断结果",
            description="输出面向客户或内部人员的诊断结论，隐藏内部 token，只展示必要设备状态和建议。",
            prompt=(
                "{{diagnosis_answer}}\n\n---\n"
                "调用链路：LLM 提取设备/异常 -> MCP 解析设备 ID -> MCP 查询最新运行数据 -> MCP 查询告警状态 -> LLM 汇总诊断。\n\n"
                "原始 MCP 摘要：\n设备解析：{{alias_payload_json}}\n最新数据：{{latest_data_json}}\n告警状态：{{alarm_data_json}}"
            ),
            outputKey="answer",
        ),
    ]
    edges = [
        {"id": "e-input-extract", "source": "input-1", "target": "llm-extract", "animated": True},
        {"id": "e-extract-alias", "source": "llm-extract", "target": "json-device-alias"},
        {"id": "e-extract-system", "source": "llm-extract", "target": "json-system-type"},
        {"id": "e-extract-anomaly", "source": "llm-extract", "target": "json-anomaly"},
        {"id": "e-extract-alarm-keyword", "source": "llm-extract", "target": "json-alarm-keyword"},
        {"id": "e-alias-resolve", "source": "json-device-alias", "target": "mcp-alias-resolve", "animated": True},
        {"id": "e-system-resolve", "source": "json-system-type", "target": "mcp-alias-resolve"},
        {"id": "e-resolve-payload", "source": "mcp-alias-resolve", "target": "json-alias-payload", "animated": True},
        {"id": "e-payload-sensor", "source": "json-alias-payload", "target": "json-sensor-id"},
        {"id": "e-sensor-latest", "source": "json-sensor-id", "target": "mcp-latest-data", "animated": True},
        {"id": "e-system-latest", "source": "json-system-type", "target": "mcp-latest-data"},
        {"id": "e-latest-payload", "source": "mcp-latest-data", "target": "json-latest-payload", "animated": True},
        {"id": "e-keyword-alarm", "source": "json-alarm-keyword", "target": "mcp-alarm-query", "animated": True},
        {"id": "e-alarm-payload", "source": "mcp-alarm-query", "target": "json-alarm-payload", "animated": True},
        {"id": "e-anomaly-diagnosis", "source": "json-anomaly", "target": "llm-diagnosis"},
        {"id": "e-alias-diagnosis", "source": "json-alias-payload", "target": "llm-diagnosis"},
        {"id": "e-latest-diagnosis", "source": "json-latest-payload", "target": "llm-diagnosis"},
        {"id": "e-alarm-diagnosis", "source": "json-alarm-payload", "target": "llm-diagnosis"},
        {"id": "e-diagnosis-output", "source": "llm-diagnosis", "target": "output-1"},
    ]
    return WorkflowPayload(name=WORKFLOW_NAME, version="0.2.0", nodes=nodes, edges=edges)


def main() -> None:
    user_id = os.getenv("SEED_WORKFLOW_USER_ID", DEFAULT_USER_ID)
    workspace_id = os.getenv("SEED_WORKFLOW_WORKSPACE_ID", DEFAULT_WORKSPACE_ID)
    payload = workflow_payload()

    engine, session_factory = create_session_factory(os.environ["DATABASE_URL"])
    store = WorkflowStore(session_factory=session_factory, engine=engine)

    with session_factory() as session:
        existing = session.scalar(
            select(DbWorkflow).where(DbWorkflow.workspace_id == workspace_id, DbWorkflow.name == WORKFLOW_NAME)
        )

    if existing:
        record = store.update_workflow(existing.id, payload, user_id, workspace_id)
        action = "updated"
    else:
        record = store.create_workflow(payload, user_id, workspace_id)
        action = "created"

    response = simulate_run(payload, SAMPLE_INPUT, user_id, workspace_id, workspace_model_configs(workspace_id))
    print(f"WORKFLOW_{action.upper()}={record.id}")
    print(f"RUN_STATUS={response.status}")
    for step in response.steps:
        print(f"STEP kind={step.kind} status={step.status} error={step.error or ''}")
    print((response.steps[-1].output or "")[:1000].replace("\n", " "))


if __name__ == "__main__":
    main()
