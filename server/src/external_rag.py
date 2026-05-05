import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import EXTERNAL_RAG_ENABLED, PAISMART_BASE_URL, PAISMART_TIMEOUT_SECONDS, PAISMART_TOKEN
from .knowledge import KnowledgeChunk


@dataclass(frozen=True)
class ExternalRagStatus:
    enabled: bool
    provider: str
    base_url: str


def external_rag_status() -> ExternalRagStatus:
    return ExternalRagStatus(
        enabled=EXTERNAL_RAG_ENABLED,
        provider="PaiSmart",
        base_url=PAISMART_BASE_URL,
    )


def paismart_configured(runtime_config: dict[str, str | bool] | None = None) -> bool:
    return bool(runtime_config and runtime_config.get("enabled")) or EXTERNAL_RAG_ENABLED


def search_paismart(
    query: str,
    top_k: int,
    runtime_config: dict[str, str | bool] | None = None,
) -> list[KnowledgeChunk]:
    if not paismart_configured(runtime_config):
        raise RuntimeError("External RAG is disabled")

    params = urlencode({"query": query, "topK": max(1, top_k)})
    base_url = str(runtime_config.get("base_url") or "").strip() if runtime_config else PAISMART_BASE_URL
    token = str(runtime_config.get("api_key") or "").strip() if runtime_config else PAISMART_TOKEN
    url = f"{base_url.rstrip('/')}/api/v1/search/hybrid?{params}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=PAISMART_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if isinstance(payload, dict):
        if payload.get("code") not in (None, 200):
            raise RuntimeError(str(payload.get("message") or "PaiSmart search failed"))
        items = payload.get("data") or []
    else:
        items = payload

    chunks: list[KnowledgeChunk] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("textContent") or item.get("text") or "").strip()
        if not text:
            continue
        file_name = item.get("fileName") or item.get("fileMd5") or "PaiSmart"
        chunk_id = item.get("chunkId")
        source = f"{file_name}#{chunk_id}" if chunk_id is not None else str(file_name)
        try:
            score = float(item.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        chunks.append(KnowledgeChunk(source=source, text=text, score=score))

    return chunks[: max(1, top_k)]
