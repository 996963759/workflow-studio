import asyncio
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar
from urllib.parse import urlparse, urlunparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


T = TypeVar("T")


class MCPGatewayError(RuntimeError):
    pass


class MCPGatewayNotConfiguredError(MCPGatewayError):
    pass


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _gateway_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MCPGatewayError("MCP_GATEWAY_URL must be a valid HTTP or HTTPS URL")
    path = parsed.path if parsed.path and parsed.path != "/" else "/mcp"
    return urlunparse(parsed._replace(path=path))


def _authorization_value() -> str:
    authorization = _env("MCP_GATEWAY_AUTHORIZATION")
    if authorization:
        return authorization
    token = _env("MCP_GATEWAY_TOKEN")
    if not token:
        return ""
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def _api_key_value() -> str:
    return _env("MCP_GATEWAY_API_KEY")


@dataclass(frozen=True)
class MCPGatewayConfig:
    url: str
    timeout_seconds: float
    headers: dict[str, str]

    @classmethod
    def from_env(cls, header_overrides: dict[str, Any] | None = None) -> "MCPGatewayConfig":
        raw_url = _env("MCP_GATEWAY_URL")
        if not raw_url:
            raise MCPGatewayNotConfiguredError("MCP gateway is not configured")

        headers = {
            "Authorization": _authorization_value(),
            "X-API-Key": _api_key_value(),
            "X-Project-Id": _env("MCP_PROJECT_ID"),
            "X-Tenant-Code": _env("MCP_TENANT_CODE"),
            "X-User-Id": _env("MCP_USER_ID"),
        }
        canonical_names = {name.lower(): name for name in headers}
        for name, value in (header_overrides or {}).items():
            canonical = canonical_names.get(str(name).strip().lower())
            if canonical and value not in (None, ""):
                headers[canonical] = str(value).strip()

        try:
            timeout_seconds = float(_env("MCP_GATEWAY_TIMEOUT_SECONDS") or "30")
        except ValueError as error:
            raise MCPGatewayError("MCP_GATEWAY_TIMEOUT_SECONDS must be a number") from error
        if timeout_seconds <= 0:
            raise MCPGatewayError("MCP_GATEWAY_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            url=_gateway_url(raw_url),
            timeout_seconds=timeout_seconds,
            headers={name: value for name, value in headers.items() if value},
        )


def mcp_gateway_configured() -> bool:
    return bool(_env("MCP_GATEWAY_URL"))


def mcp_gateway_status() -> dict[str, Any]:
    if not mcp_gateway_configured():
        return {"configured": False, "endpoint": None}
    try:
        config = MCPGatewayConfig.from_env()
    except MCPGatewayError as error:
        return {"configured": False, "endpoint": None, "error": str(error)}
    parsed = urlparse(config.url)
    return {
        "configured": True,
        "endpoint": f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
        "project_configured": "X-Project-Id" in config.headers,
        "tenant_configured": "X-Tenant-Code" in config.headers,
        "user_configured": "X-User-Id" in config.headers,
        "authorization_configured": "Authorization" in config.headers,
        "api_key_configured": "X-API-Key" in config.headers,
    }


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _model_dump(item) for key, item in value.items()}
    return value


async def _with_session(
    action: Callable[[ClientSession], Awaitable[T]],
    header_overrides: dict[str, Any] | None = None,
) -> T:
    config = MCPGatewayConfig.from_env(header_overrides)
    try:
        async with httpx.AsyncClient(
            headers=config.headers,
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=True,
        ) as http_client:
            async with streamable_http_client(config.url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await action(session)
    except MCPGatewayError:
        raise
    except Exception as error:  # noqa: BLE001 - translated into a stable workflow error.
        message = str(error).strip() or error.__class__.__name__
        raise MCPGatewayError(f"MCP gateway request failed: {message}") from error


async def _list_tools(header_overrides: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async def action(session: ClientSession) -> list[dict[str, Any]]:
        result = await session.list_tools()
        tools: list[dict[str, Any]] = []
        for tool in result.tools:
            raw = _model_dump(tool)
            tools.append(
                {
                    "name": raw.get("name", ""),
                    "description": raw.get("description", ""),
                    "input_schema": raw.get("inputSchema", raw.get("input_schema", {})),
                    "annotations": raw.get("annotations") or {},
                    "source": "gateway",
                }
            )
        return tools

    return await _with_session(action, header_overrides)


async def _call_tool(
    name: str,
    arguments: dict[str, Any],
    header_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async def action(session: ClientSession) -> dict[str, Any]:
        result = await session.call_tool(name, arguments=arguments)
        raw = _model_dump(result)
        structured = raw.get("structuredContent", raw.get("structured_content"))
        content = structured if structured is not None else raw.get("content", [])
        failed = bool(raw.get("isError", raw.get("is_error", False)))
        return {
            "tool": name,
            "status": "error" if failed else "ok",
            "data": content,
            "is_error": failed,
            "source": "gateway",
        }

    return await _with_session(action, header_overrides)


def _run(coro: Awaitable[T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise MCPGatewayError("MCP gateway calls must run outside an active asyncio event loop")


def list_gateway_tools(header_overrides: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _run(_list_tools(header_overrides))


def call_gateway_tool(
    name: str,
    arguments: dict[str, Any],
    header_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not name.strip():
        raise MCPGatewayError("MCP tool name is required")
    return _run(_call_tool(name.strip(), arguments, header_overrides))
