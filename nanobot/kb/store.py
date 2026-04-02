"""Lightweight file-backed knowledge store with permission filtering."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nanobot.utils.helpers import ensure_dir


def _tokenize(text: str) -> set[str]:
    normalized = re.sub(r"[^\w\s]", " ", text or "", flags=re.UNICODE)
    return {
        tok.lower()
        for tok in normalized.replace("\n", " ").split()
        if tok.strip()
    }


def _score(query_tokens: set[str], text: str) -> int:
    if not query_tokens:
        return 0
    text_tokens = _tokenize(text)
    return len(query_tokens & text_tokens)


@dataclass
class KnowledgeChunk:
    """A single chunk in the knowledge base."""

    doc_id: str
    chunk_id: str
    content: str
    source: str
    updated_at: str
    tenant_id: str = "default"
    visibility: str = "public"  # public | team | private
    owner_id: str = ""
    team_id: str = ""
    tags: list[str] = field(default_factory=list)
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "content": self.content,
            "source": self.source,
            "updated_at": self.updated_at,
            "tenant_id": self.tenant_id,
            "visibility": self.visibility,
            "owner_id": self.owner_id,
            "team_id": self.team_id,
            "tags": self.tags,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeChunk":
        return cls(
            doc_id=data.get("doc_id", ""),
            chunk_id=data.get("chunk_id", ""),
            content=data.get("content", ""),
            source=data.get("source", ""),
            updated_at=data.get("updated_at", ""),
            tenant_id=data.get("tenant_id", "default"),
            visibility=data.get("visibility", "public"),
            owner_id=data.get("owner_id", ""),
            team_id=data.get("team_id", ""),
            tags=list(data.get("tags", [])),
            content_hash=data.get("content_hash", ""),
        )


class KnowledgeStore:
    """Simple JSONL-based knowledge store."""

    def __init__(self, workspace: Path, max_chunk_chars: int = 1200):
        self.workspace = workspace
        self.max_chunk_chars = max_chunk_chars
        self.kb_dir = ensure_dir(workspace / "kb")
        self.kb_file = self.kb_dir / "chunks.jsonl"

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _chunk_text(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self.max_chunk_chars:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chunk_chars, len(text))
            chunks.append(text[start:end].strip())
            start = end
        return [c for c in chunks if c]

    def _load_chunks(self) -> list[KnowledgeChunk]:
        if not self.kb_file.exists():
            return []
        chunks: list[KnowledgeChunk] = []
        with open(self.kb_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunks.append(KnowledgeChunk.from_dict(json.loads(line)))
                except Exception:
                    continue
        return chunks

    def _save_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        ensure_dir(self.kb_file.parent)
        with open(self.kb_file, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")

    def upsert_document(
        self,
        *,
        doc_id: str,
        content: str,
        source: str,
        updated_at: str,
        tenant_id: str = "default",
        visibility: str = "public",
        owner_id: str = "",
        team_id: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, int]:
        chunks = self._load_chunks()
        existing = [c for c in chunks if c.doc_id != doc_id]

        new_chunks_text = self._chunk_text(content)
        new_chunks: list[KnowledgeChunk] = []
        for idx, chunk_text in enumerate(new_chunks_text):
            new_chunks.append(
                KnowledgeChunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}#{idx}",
                    content=chunk_text,
                    source=source,
                    updated_at=updated_at,
                    tenant_id=tenant_id or "default",
                    visibility=visibility or "public",
                    owner_id=owner_id,
                    team_id=team_id,
                    tags=tags or [],
                    content_hash=self._content_hash(chunk_text),
                )
            )

        self._save_chunks(existing + new_chunks)
        return {"deleted": len(chunks) - len(existing), "upserted": len(new_chunks)}

    def delete_document(self, doc_id: str) -> int:
        chunks = self._load_chunks()
        kept = [c for c in chunks if c.doc_id != doc_id]
        removed = len(chunks) - len(kept)
        self._save_chunks(kept)
        return removed

    @staticmethod
    def _can_access(
        chunk: KnowledgeChunk,
        *,
        tenant_id: str,
        user_id: str,
        team_ids: set[str],
    ) -> bool:
        if chunk.tenant_id != tenant_id:
            return False
        if chunk.visibility == "public":
            return True
        if chunk.visibility == "private":
            return bool(user_id) and chunk.owner_id == user_id
        if chunk.visibility == "team":
            return bool(chunk.team_id) and chunk.team_id in team_ids
        return False

    def search(
        self,
        *,
        query: str,
        tenant_id: str = "default",
        user_id: str = "",
        team_ids: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        q_tokens = _tokenize(query)
        allowed_team_ids = {t for t in (team_ids or []) if t}
        results: list[tuple[int, KnowledgeChunk]] = []
        for chunk in self._load_chunks():
            if not self._can_access(
                chunk,
                tenant_id=tenant_id or "default",
                user_id=user_id,
                team_ids=allowed_team_ids,
            ):
                continue
            score = _score(q_tokens, chunk.content)
            if score <= 0:
                continue
            results.append((score, chunk))

        results.sort(key=lambda x: x[0], reverse=True)
        top = results[: max(1, min(limit, 20))]
        return [
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "source": chunk.source,
                "updated_at": chunk.updated_at,
                "score": score,
                "tenant_id": chunk.tenant_id,
                "visibility": chunk.visibility,
                "owner_id": chunk.owner_id,
                "team_id": chunk.team_id,
                "tags": chunk.tags,
            }
            for score, chunk in top
        ]
