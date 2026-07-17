import json
import os
from typing import Any

from .mcp_gateway import call_gateway_tool, list_gateway_tools, mcp_gateway_configured


class MCPToolNotFoundError(ValueError):
    pass


def building_bms_get_device_status(arguments: dict[str, Any]) -> dict[str, Any]:
    device_id = str(arguments.get("device_id") or "AHU-18F-07").strip() or "AHU-18F-07"
    building = str(arguments.get("building") or "A座").strip() or "A座"
    floor = str(arguments.get("floor") or "18F").strip() or "18F"
    device_status = {
        "device_id": device_id,
        "device_name": f"{building}{floor}新风机组控制器",
        "system": "HVAC/BMS",
        "building": building,
        "floor": floor,
        "area": "东区会议区",
        "gateway_id": "BMS-GW-A-18F-02",
        "switch_port": "Gi1/0/18",
        "connection_status": "offline",
        "offline_minutes": 31,
        "last_seen": "2026-07-14 09:02:18",
        "alarm_level": "P1",
        "alarm_code": "BACNET_HEARTBEAT_TIMEOUT",
        "bacnet_status": "timeout",
        "mqtt_status": "disconnected",
        "co2_ppm": 1380,
        "supply_air_temp": 19.2,
        "return_air_temp": 26.5,
        "damper_position": 15,
        "fan_status": "unknown",
        "recent_events": [
            "08:36 BACnet 轮询延迟 2200ms",
            "08:47 网关重连 2 次",
            "09:02 最后一次心跳",
            "09:05 触发设备离线告警",
            "09:08 会议区 CO2 超过 1200ppm",
        ],
        "owner_team": "楼宇自控运维二组",
    }
    return {
        "tool": "mcp.building_bms.get_device_status",
        "status": "ok",
        "query": arguments,
        "data": device_status,
    }


MCP_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "mcp.building_bms.get_device_status": {
        "name": "mcp.building_bms.get_device_status",
        "description": "查询智能楼宇 BMS 中指定设备的连接状态、告警和关键环境指标。",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "设备编号，例如 AHU-18F-07"},
                "building": {"type": "string", "description": "楼栋，例如 A座"},
                "floor": {"type": "string", "description": "楼层，例如 18F"},
                "source": {"type": "string", "description": "LLM 识别出的查询上下文"},
            },
            "required": ["device_id"],
        },
    },
}


def list_mcp_tools() -> list[dict[str, Any]]:
    return list(MCP_TOOL_DEFINITIONS.values())


def list_available_mcp_tools(header_overrides: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    local_tools = [{**item, "source": "local"} for item in list_mcp_tools()]
    if not mcp_gateway_configured():
        return local_tools
    remote_tools = list_gateway_tools(header_overrides)
    local_names = {item["name"] for item in local_tools}
    return local_tools + [item for item in remote_tools if item.get("name") not in local_names]


def is_mcp_tool_name(name: Any, tool_url: Any = None) -> bool:
    normalized = str(name or "").strip()
    if normalized in MCP_TOOL_DEFINITIONS:
        return True
    return bool(normalized and not str(tool_url or "").strip() and mcp_gateway_configured())


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _business_token_from_env() -> str:
    token = _env("MCP_TOOL_TOKEN")
    if token:
        return token if token.lower().startswith("bearer ") else f"Bearer {token}"

    authorization = _env("MCP_GATEWAY_AUTHORIZATION")
    if authorization:
        return authorization

    gateway_token = _env("MCP_GATEWAY_TOKEN")
    if gateway_token:
        return gateway_token if gateway_token.lower().startswith("bearer ") else f"Bearer {gateway_token}"

    return ""


def _with_neuron_task_defaults(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not name.startswith("neuron-task-mcp."):
        return arguments

    updated = dict(arguments)
    current_token = str(updated.get("token") or "").strip()
    if current_token in {"", "REPLACE_WITH_USER_TOKEN"}:
        token = _business_token_from_env()
        if token:
            updated["token"] = token

    current_project = str(updated.get("projectId") or updated.get("project_id") or "").strip()
    if current_project in {"", "REPLACE_WITH_PROJECT_ID"}:
        project_id = _env("MCP_PROJECT_ID")
        if project_id:
            updated["projectId"] = project_id

    return updated


def call_mcp_tool(
    name: str,
    arguments: dict[str, Any],
    header_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if name == "mcp.building_bms.get_device_status":
        return building_bms_get_device_status(arguments)
    if mcp_gateway_configured():
        return call_gateway_tool(name, _with_neuron_task_defaults(name, arguments), header_overrides)
    raise MCPToolNotFoundError(f"Unknown MCP tool: {name}")


def format_mcp_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
