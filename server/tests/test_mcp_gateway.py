import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from server.src import mcp_tools, runner
from server.src.mcp_gateway import MCPGatewayConfig, call_gateway_tool, list_gateway_tools


class _MCPTestHandler(BaseHTTPRequestHandler):
    received_headers: list[dict[str, str]] = []

    def log_message(self, _format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        self.send_response(405)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.received_headers.append({name: value for name, value in self.headers.items()})
        method = payload.get("method")

        if method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if method == "initialize":
            result = {
                "protocolVersion": payload.get("params", {}).get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "workflow-studio-test-gateway", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "neuron-task-mcp.GetSchedulePage",
                        "description": "List maintenance schedules",
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True},
                    }
                ]
            }
        elif method == "tools/call":
            result = {
                "content": [{"type": "text", "text": "schedule-1"}],
                "structuredContent": {"records": [{"id": "schedule-1"}]},
                "isError": False,
            }
        else:
            self.send_response(400)
            self.end_headers()
            return

        body = json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "result": result}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MCPGatewayConfigTests(unittest.TestCase):
    def test_config_uses_company_gateway_headers_and_default_path(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MCP_GATEWAY_URL": "https://mcp.example.internal",
                "MCP_GATEWAY_AUTHORIZATION": "",
                "MCP_GATEWAY_TOKEN": "test-token",
                "MCP_GATEWAY_API_KEY": "test-api-key",
                "MCP_PROJECT_ID": "project-a",
                "MCP_TENANT_CODE": "tenant-a",
                "MCP_USER_ID": "user-a",
            },
            clear=False,
        ):
            config = MCPGatewayConfig.from_env({"X-Project-Id": "project-node"})

        self.assertEqual(config.url, "https://mcp.example.internal/mcp")
        self.assertEqual(config.headers["Authorization"], "Bearer test-token")
        self.assertEqual(config.headers["X-API-Key"], "test-api-key")
        self.assertEqual(config.headers["X-Project-Id"], "project-node")
        self.assertEqual(config.headers["X-Tenant-Code"], "tenant-a")
        self.assertEqual(config.headers["X-User-Id"], "user-a")

    def test_remote_tool_node_dispatches_to_gateway(self) -> None:
        gateway_result = {
            "tool": "neuron-task-mcp.GetSchedulePage",
            "status": "ok",
            "data": {"records": [{"id": "schedule-1"}]},
            "source": "gateway",
        }
        with (
            patch.dict(
                os.environ,
                {
                    "MCP_GATEWAY_URL": "https://mcp.example.internal/mcp",
                    "MCP_PROJECT_ID": "",
                },
                clear=False,
            ),
            patch("server.src.mcp_tools.call_gateway_tool", return_value=gateway_result) as gateway_call,
        ):
            output, step_input, error = runner.run_mcp_tool_node(
                {
                    "toolName": "neuron-task-mcp.GetSchedulePage",
                    "toolParams": '{"pageNum":1,"pageSize":10,"token":"argument-secret"}',
                    "toolHeaders": '{"X-Project-Id":"project-a","Authorization":"Bearer secret"}',
                },
                {},
            )

        self.assertIsNone(error)
        self.assertIn('"source": "gateway"', output)
        self.assertIn('"Authorization": "***"', step_input)
        self.assertIn('"token": "***"', step_input)
        self.assertNotIn("argument-secret", step_input)
        gateway_call.assert_called_once_with(
            "neuron-task-mcp.GetSchedulePage",
            {"pageNum": 1, "pageSize": 10, "token": "argument-secret"},
            {"X-Project-Id": "project-a", "Authorization": "Bearer secret"},
        )

    def test_neuron_task_tool_uses_configured_identity_defaults(self) -> None:
        gateway_result = {
            "tool": "neuron-task-mcp.GetSchedulePage",
            "status": "ok",
            "data": {"records": [{"id": "schedule-1"}]},
            "source": "gateway",
        }
        with (
            patch.dict(
                os.environ,
                {
                    "MCP_GATEWAY_URL": "https://mcp.example.internal/mcp",
                    "MCP_GATEWAY_AUTHORIZATION": "Bearer business-token",
                    "MCP_PROJECT_ID": "project-env",
                },
                clear=False,
            ),
            patch("server.src.mcp_tools.call_gateway_tool", return_value=gateway_result) as gateway_call,
        ):
            output, step_input, error = runner.run_mcp_tool_node(
                {
                    "toolName": "neuron-task-mcp.GetSchedulePage",
                    "toolParams": '{"projectId":"REPLACE_WITH_PROJECT_ID","pageSize":10}',
                    "toolHeaders": "{}",
                },
                {},
            )

        self.assertIsNone(error)
        self.assertIn('"source": "gateway"', output)
        self.assertNotIn("business-token", step_input)
        gateway_call.assert_called_once_with(
            "neuron-task-mcp.GetSchedulePage",
            {"projectId": "project-env", "pageSize": 10, "token": "Bearer business-token"},
            {},
        )

    def test_gateway_tool_name_is_recognized_without_tool_url(self) -> None:
        with patch.dict(os.environ, {"MCP_GATEWAY_URL": "https://mcp.example.internal/mcp"}, clear=False):
            self.assertTrue(mcp_tools.is_mcp_tool_name("neuron-task-mcp.GetSchedulePage"))
            self.assertFalse(
                mcp_tools.is_mcp_tool_name(
                    "neuron-task-mcp.GetSchedulePage",
                    "http://127.0.0.1:8000/api/tool",
                )
            )

    def test_json_node_accepts_fenced_model_json(self) -> None:
        output, step_input = runner.run_json_node(
            {
                "jsonSource": '```json\n{"device_alias":"2号空调-大门右3","meta":{"system_type":"Bms"}}\n```',
                "jsonPath": "meta.system_type",
            },
            {},
        )

        self.assertEqual(output, "Bms")
        self.assertIn("device_alias", step_input)

    def test_streamable_http_transport_lists_and_calls_real_tools(self) -> None:
        _MCPTestHandler.received_headers = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPTestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(
                os.environ,
                {
                    "MCP_GATEWAY_URL": f"http://127.0.0.1:{server.server_port}/mcp",
                    "MCP_GATEWAY_AUTHORIZATION": "Bearer transport-token",
                    "MCP_GATEWAY_API_KEY": "transport-api-key",
                    "MCP_PROJECT_ID": "project-transport",
                    "MCP_TENANT_CODE": "tenant-transport",
                    "MCP_USER_ID": "user-transport",
                },
                clear=False,
            ):
                tools = list_gateway_tools()
                result = call_gateway_tool("neuron-task-mcp.GetSchedulePage", {"pageNum": 1})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(tools[0]["name"], "neuron-task-mcp.GetSchedulePage")
        self.assertEqual(result["data"]["records"][0]["id"], "schedule-1")
        self.assertTrue(_MCPTestHandler.received_headers)
        headers = _MCPTestHandler.received_headers[0]
        self.assertEqual(headers["Authorization"], "Bearer transport-token")
        self.assertEqual(headers["X-API-Key"], "transport-api-key")
        self.assertEqual(headers["X-Project-Id"], "project-transport")
        self.assertEqual(headers["X-Tenant-Code"], "tenant-transport")
        self.assertEqual(headers["X-User-Id"], "user-transport")


if __name__ == "__main__":
    unittest.main()
