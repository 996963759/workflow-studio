import re
from dataclasses import dataclass
from pathlib import Path


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge"
SUPPORTED_EXTENSIONS = {".md", ".txt"}
MAX_CHUNK_CHARS = 900


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    text: str
    score: int


def tokenize(value: str) -> list[str]:
    tokens: list[str] = []
    for item in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", value):
        text = item.lower().strip()
        if not text:
            continue
        tokens.append(text)
        if re.fullmatch(r"[\u4e00-\u9fff]+", text):
            tokens.extend(text[index : index + 2] for index in range(len(text) - 1))
            tokens.extend(text)
    return list(dict.fromkeys(tokens))


def split_document(content: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    chunks: list[str] = []

    for block in blocks:
        if len(block) <= MAX_CHUNK_CHARS:
            chunks.append(block)
            continue
        for index in range(0, len(block), MAX_CHUNK_CHARS):
            chunk = block[index : index + MAX_CHUNK_CHARS].strip()
            if chunk:
                chunks.append(chunk)

    return chunks


def read_knowledge_documents() -> list[tuple[str, str]]:
    if not KNOWLEDGE_DIR.exists():
        return []

    documents: list[tuple[str, str]] = []
    for path in sorted(KNOWLEDGE_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            content = path.read_text(encoding="gb18030", errors="ignore").strip()
        if content:
            documents.append((path.relative_to(KNOWLEDGE_DIR).as_posix(), content))
    return documents


def score_chunk(query_tokens: list[str], text: str) -> int:
    lower_text = text.lower()
    return sum(lower_text.count(token) for token in query_tokens)


def search_knowledge(query: str, top_k: int) -> list[KnowledgeChunk]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    matches: list[KnowledgeChunk] = []
    for source, content in read_knowledge_documents():
        for chunk in split_document(content):
            score = score_chunk(query_tokens, chunk)
            if score > 0:
                matches.append(KnowledgeChunk(source=source, text=chunk, score=score))

    return sorted(matches, key=lambda item: (-item.score, item.source, item.text[:40]))[: max(1, top_k)]


def knowledge_status() -> dict[str, int | str]:
    documents = read_knowledge_documents()
    chunk_count = sum(len(split_document(content)) for _, content in documents)
    return {
        "directory": str(KNOWLEDGE_DIR),
        "document_count": len(documents),
        "chunk_count": chunk_count,
    }
