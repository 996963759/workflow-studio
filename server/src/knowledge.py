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


def safe_document_name(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise ValueError("Document filename is required")
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("Only .md and .txt documents are supported")
    safe_name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", name)
    if safe_name in {".", ".."}:
        raise ValueError("Invalid document filename")
    return safe_name


def user_knowledge_dir(user_id: str | None = None) -> Path:
    if not user_id:
        return KNOWLEDGE_DIR
    safe_user = re.sub(r"[^A-Za-z0-9._-]+", "-", user_id)
    return KNOWLEDGE_DIR / safe_user


def document_path(filename: str, user_id: str | None = None) -> Path:
    safe_name = safe_document_name(filename)
    root = user_knowledge_dir(user_id).resolve()
    path = (root / safe_name).resolve()
    if root not in path.parents and path != root:
        raise ValueError("Invalid document path")
    return path


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


def read_knowledge_documents(user_id: str | None = None) -> list[tuple[str, str]]:
    root = user_knowledge_dir(user_id)
    if not root.exists():
        return []

    documents: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            content = path.read_text(encoding="gb18030", errors="ignore").strip()
        if content:
            documents.append((path.relative_to(root).as_posix(), content))
    return documents


def list_knowledge_documents(user_id: str | None = None) -> list[dict[str, int | str]]:
    documents: list[dict[str, int | str]] = []
    root = user_knowledge_dir(user_id)
    if not root.exists():
        return documents

    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        documents.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "chunk_count": len(split_document(content)),
            }
        )
    return documents


def save_knowledge_document(filename: str, content: str, user_id: str | None = None) -> dict[str, int | str]:
    if len(content.encode("utf-8")) > 1_000_000:
        raise ValueError("Document is too large")
    path = document_path(filename, user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "chunk_count": len(split_document(content)),
    }


def delete_knowledge_document(filename: str, user_id: str | None = None) -> bool:
    path = document_path(filename, user_id)
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    return True


def score_chunk(query_tokens: list[str], text: str) -> int:
    lower_text = text.lower()
    return sum(lower_text.count(token) for token in query_tokens)


def search_knowledge(query: str, top_k: int, user_id: str | None = None) -> list[KnowledgeChunk]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    matches: list[KnowledgeChunk] = []
    for source, content in read_knowledge_documents(user_id):
        for chunk in split_document(content):
            score = score_chunk(query_tokens, chunk)
            if score > 0:
                matches.append(KnowledgeChunk(source=source, text=chunk, score=score))

    return sorted(matches, key=lambda item: (-item.score, item.source, item.text[:40]))[: max(1, top_k)]


def knowledge_status(user_id: str | None = None) -> dict[str, int | str]:
    root = user_knowledge_dir(user_id)
    documents = read_knowledge_documents(user_id)
    chunk_count = sum(len(split_document(content)) for _, content in documents)
    return {
        "directory": str(root),
        "document_count": len(documents),
        "chunk_count": chunk_count,
    }
