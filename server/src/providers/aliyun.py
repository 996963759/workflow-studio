import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/")
DASHSCOPE_TIMEOUT_SECONDS = float(os.getenv("DASHSCOPE_TIMEOUT_SECONDS", "60"))
DASHSCOPE_POLL_INTERVAL_SECONDS = float(os.getenv("DASHSCOPE_POLL_INTERVAL_SECONDS", "1.5"))
DASHSCOPE_MAX_POLL_SECONDS = float(os.getenv("DASHSCOPE_MAX_POLL_SECONDS", "90"))
DEFAULT_TTS_MODEL = os.getenv("ALIYUN_TTS_MODEL", "cosyvoice-v2")
DEFAULT_IMAGE_MODEL = os.getenv("ALIYUN_IMAGE_MODEL", "wanx2.1-t2i-turbo")


class AliyunProviderError(RuntimeError):
    pass


def dashscope_api_key() -> str:
    return os.getenv("DASHSCOPE_API_KEY", "").strip()


def aliyun_configured() -> bool:
    return bool(dashscope_api_key())


def _request_json(path: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    api_key = dashscope_api_key()
    if not api_key:
        raise AliyunProviderError("DASHSCOPE_API_KEY is not configured")

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        f"{DASHSCOPE_BASE_URL}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(headers or {}),
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=DASHSCOPE_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise AliyunProviderError(f"DashScope HTTP {error.code}: {detail[:300]}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise AliyunProviderError(str(error)) from error


def _extract_audio_url(body: dict[str, Any]) -> str | None:
    output = body.get("output")
    if isinstance(output, dict):
        audio = output.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("url"), str):
            return audio["url"]
        if isinstance(output.get("url"), str):
            return output["url"]
    return None


def run_tts(
    text: str,
    model: str = DEFAULT_TTS_MODEL,
    voice: str = "longxiaochun",
    audio_format: str = "mp3",
    speech_rate: float = 1.0,
) -> tuple[str, str]:
    payload = {
        "model": model or DEFAULT_TTS_MODEL,
        "input": {
            "text": text,
            "voice": voice or "longxiaochun",
        },
        "parameters": {
            "format": audio_format or "mp3",
            "speech_rate": speech_rate,
        },
    }
    body = _request_json("/api/v1/services/aigc/multimodal-generation/generation", payload)
    audio_url = _extract_audio_url(body)
    if not audio_url:
        raise AliyunProviderError(f"DashScope TTS response did not include audio url: {json.dumps(body, ensure_ascii=False)[:300]}")
    return audio_url, str(payload["model"])


def _extract_task_id(body: dict[str, Any]) -> str | None:
    output = body.get("output")
    if isinstance(output, dict) and isinstance(output.get("task_id"), str):
        return output["task_id"]
    if isinstance(body.get("task_id"), str):
        return body["task_id"]
    return None


def _extract_image_urls(body: dict[str, Any]) -> list[str]:
    output = body.get("output")
    results = output.get("results") if isinstance(output, dict) else None
    if isinstance(results, list):
        urls = [item.get("url") for item in results if isinstance(item, dict) and isinstance(item.get("url"), str)]
        if urls:
            return urls
    if isinstance(output, dict) and isinstance(output.get("url"), str):
        return [output["url"]]
    return []


def _poll_task(task_id: str) -> dict[str, Any]:
    deadline = time.time() + DASHSCOPE_MAX_POLL_SECONDS
    last_body: dict[str, Any] = {}
    while time.time() < deadline:
        body = _request_json(f"/api/v1/tasks/{task_id}")
        last_body = body
        output = body.get("output")
        status = output.get("task_status") if isinstance(output, dict) else None
        if status == "SUCCEEDED":
            return body
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            raise AliyunProviderError(f"DashScope task {status}: {json.dumps(body, ensure_ascii=False)[:300]}")
        time.sleep(DASHSCOPE_POLL_INTERVAL_SECONDS)
    raise AliyunProviderError(f"DashScope task timed out: {json.dumps(last_body, ensure_ascii=False)[:300]}")


def run_image_generation(
    prompt: str,
    model: str = DEFAULT_IMAGE_MODEL,
    size: str = "1024*1024",
    count: int = 1,
) -> tuple[list[str], str]:
    payload = {
        "model": model or DEFAULT_IMAGE_MODEL,
        "input": {"prompt": prompt},
        "parameters": {
            "size": size or "1024*1024",
            "n": max(1, min(int(count or 1), 4)),
        },
    }
    body = _request_json(
        "/api/v1/services/aigc/text2image/image-synthesis",
        payload,
        {"X-DashScope-Async": "enable"},
    )
    task_id = _extract_task_id(body)
    if not task_id:
        raise AliyunProviderError(f"DashScope image response did not include task_id: {json.dumps(body, ensure_ascii=False)[:300]}")
    result = _poll_task(task_id)
    urls = _extract_image_urls(result)
    if not urls:
        raise AliyunProviderError(f"DashScope image task did not include image urls: {json.dumps(result, ensure_ascii=False)[:300]}")
    return urls, str(payload["model"])
