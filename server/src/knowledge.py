import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from .db import SessionLocal
from .orm import DbKnowledgeChunk
from .storage import utc_now


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge"
SUPPORTED_EXTENSIONS = {".md", ".txt"}
MAX_CHUNK_CHARS = 900
VECTOR_DIMENSIONS = 64
KnowledgeSessionLocal: sessionmaker[Session] = SessionLocal


def set_knowledge_session_factory(session_factory: sessionmaker[Session]) -> None:
    global KnowledgeSessionLocal
    KnowledgeSessionLocal = session_factory


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    text: str
    score: float


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


def user_knowledge_dir(user_id: str | None = None, workspace_id: str | None = None) -> Path:
    if not user_id:
        return KNOWLEDGE_DIR
    safe_user = re.sub(r"[^A-Za-z0-9._-]+", "-", user_id)
    if not workspace_id:
        return KNOWLEDGE_DIR / safe_user
    safe_workspace = re.sub(r"[^A-Za-z0-9._-]+", "-", workspace_id)
    return KNOWLEDGE_DIR / safe_user / safe_workspace


def document_path(filename: str, user_id: str | None = None, workspace_id: str | None = None) -> Path:
    safe_name = safe_document_name(filename)
    root = user_knowledge_dir(user_id, workspace_id).resolve()
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


def embed_text(value: str) -> list[float]:
    vector = [0.0] * VECTOR_DIMENSIONS
    for token in tokenize(value):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % VECTOR_DIMENSIONS
        weight = 1.0 + min(len(token), 12) / 12
        vector[index] += weight
    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0:
        return vector
    return [round(item / norm, 6) for item in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def index_knowledge_document(
    filename: str,
    content: str,
    user_id: str,
    workspace_id: str,
) -> int:
    chunks = split_document(content)
    now = utc_now()
    with KnowledgeSessionLocal() as session:
        session.execute(
            delete(DbKnowledgeChunk).where(
                DbKnowledgeChunk.user_id == user_id,
                DbKnowledgeChunk.workspace_id == workspace_id,
                DbKnowledgeChunk.document_name == filename,
            )
        )
        for index, chunk in enumerate(chunks):
            session.add(
                DbKnowledgeChunk(
                    id=f"{workspace_id}:{filename}:{index}",
                    user_id=user_id,
                    workspace_id=workspace_id,
                    document_name=filename,
                    chunk_index=index,
                    text=chunk,
                    vector_json=json.dumps(embed_text(chunk), separators=(",", ":")),
                    updated_at=now,
                )
            )
        session.commit()
    return len(chunks)


def delete_knowledge_index(filename: str, user_id: str, workspace_id: str) -> None:
    with KnowledgeSessionLocal() as session:
        session.execute(
            delete(DbKnowledgeChunk).where(
                DbKnowledgeChunk.user_id == user_id,
                DbKnowledgeChunk.workspace_id == workspace_id,
                DbKnowledgeChunk.document_name == filename,
            )
        )
        session.commit()


def ensure_workspace_index(user_id: str, workspace_id: str) -> None:
    with KnowledgeSessionLocal() as session:
        existing_count = session.scalar(
            select(DbKnowledgeChunk.id)
            .where(DbKnowledgeChunk.user_id == user_id, DbKnowledgeChunk.workspace_id == workspace_id)
            .limit(1)
        )
    if existing_count:
        return
    for source, content in read_knowledge_documents(user_id, workspace_id):
        index_knowledge_document(source, content, user_id, workspace_id)


def read_knowledge_documents(user_id: str | None = None, workspace_id: str | None = None) -> list[tuple[str, str]]:
    root = user_knowledge_dir(user_id, workspace_id)
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


def list_knowledge_documents(user_id: str | None = None, workspace_id: str | None = None) -> list[dict[str, int | str]]:
    documents: list[dict[str, int | str]] = []
    root = user_knowledge_dir(user_id, workspace_id)
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


def save_knowledge_document(
    filename: str,
    content: str,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, int | str]:
    if len(content.encode("utf-8")) > 1_000_000:
        raise ValueError("Document is too large")
    path = document_path(filename, user_id, workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    chunk_count = len(split_document(content))
    if user_id and workspace_id:
        chunk_count = index_knowledge_document(path.name, content, user_id, workspace_id)
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "chunk_count": chunk_count,
    }


def delete_knowledge_document(filename: str, user_id: str | None = None, workspace_id: str | None = None) -> bool:
    path = document_path(filename, user_id, workspace_id)
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    if user_id and workspace_id:
        delete_knowledge_index(path.name, user_id, workspace_id)
    return True


def score_chunk(query_tokens: list[str], text: str) -> int:
    lower_text = text.lower()
    return sum(lower_text.count(token) for token in query_tokens)


def search_knowledge(
    query: str,
    top_k: int,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> list[KnowledgeChunk]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    matches: list[KnowledgeChunk] = []
    if user_id and workspace_id:
        ensure_workspace_index(user_id, workspace_id)
        query_vector = embed_text(query)
        with KnowledgeSessionLocal() as session:
            rows = session.scalars(
                select(DbKnowledgeChunk).where(
                    DbKnowledgeChunk.user_id == user_id,
                    DbKnowledgeChunk.workspace_id == workspace_id,
                )
            ).all()
        for row in rows:
            keyword_score = score_chunk(query_tokens, row.text)
            vector_score = cosine_similarity(query_vector, json.loads(row.vector_json))
            score = keyword_score + vector_score
            if score > 0:
                matches.append(KnowledgeChunk(source=row.document_name, text=row.text, score=round(score, 4)))
        return sorted(matches, key=lambda item: (-item.score, item.source, item.text[:40]))[: max(1, top_k)]

    for source, content in read_knowledge_documents(user_id, workspace_id):
        for chunk in split_document(content):
            score = score_chunk(query_tokens, chunk)
            if score > 0:
                matches.append(KnowledgeChunk(source=source, text=chunk, score=score))

    return sorted(matches, key=lambda item: (-item.score, item.source, item.text[:40]))[: max(1, top_k)]


def knowledge_status(user_id: str | None = None, workspace_id: str | None = None) -> dict[str, int | str]:
    root = user_knowledge_dir(user_id, workspace_id)
    documents = read_knowledge_documents(user_id, workspace_id)
    chunk_count = sum(len(split_document(content)) for _, content in documents)
    indexed_chunk_count = 0
    if user_id and workspace_id:
        ensure_workspace_index(user_id, workspace_id)
        with KnowledgeSessionLocal() as session:
            indexed_chunk_count = len(
                session.scalars(
                    select(DbKnowledgeChunk.id).where(
                        DbKnowledgeChunk.user_id == user_id,
                        DbKnowledgeChunk.workspace_id == workspace_id,
                    )
                ).all()
            )
    return {
        "directory": str(root),
        "document_count": len(documents),
        "chunk_count": chunk_count,
        "indexed_chunk_count": indexed_chunk_count,
    }
