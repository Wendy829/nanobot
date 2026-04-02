"""Knowledge base tools for ingesting and retrieving internal documents."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.kb.store import KnowledgeStore


def _parse_team_ids(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [s.strip() for s in raw.split(",") if s.strip()]
    return []


class KBIngestTool(Tool):
    """Tool to ingest or update knowledge-base documents."""

    def __init__(self, store: KnowledgeStore):
        self.store = store

    @property
    def name(self) -> str:
        return "kb_ingest"

    @property
    def description(self) -> str:
        return (
            "Ingest or update an internal knowledge document for enterprise Q&A. "
            "Use visibility=public/team/private and tenant_id for access control."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Stable document ID"},
                "content": {"type": "string", "description": "Document content"},
                "source": {"type": "string", "description": "Document source URI/path/title"},
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "visibility": {
                    "type": "string",
                    "enum": ["public", "team", "private"],
                    "description": "Visibility scope",
                },
                "owner_id": {"type": "string", "description": "Owner user ID (for private docs)"},
                "team_id": {"type": "string", "description": "Team ID (for team docs)"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "updated_at": {"type": "string", "description": "ISO timestamp"},
            },
            "required": ["doc_id", "content", "source"],
        }

    async def execute(
        self,
        doc_id: str,
        content: str,
        source: str,
        tenant_id: str = "default",
        visibility: str = "public",
        owner_id: str = "",
        team_id: str = "",
        tags: list[str] | None = None,
        updated_at: str | None = None,
        **kwargs: Any,
    ) -> str:
        result = self.store.upsert_document(
            doc_id=doc_id,
            content=content,
            source=source,
            updated_at=updated_at or datetime.now().isoformat(),
            tenant_id=tenant_id or "default",
            visibility=visibility,
            owner_id=owner_id,
            team_id=team_id,
            tags=tags or [],
        )
        return (
            f"KB document upserted: doc_id={doc_id}, tenant_id={tenant_id or 'default'}, "
            f"chunks={result['upserted']}, replaced={result['deleted']}"
        )


class KBSearchTool(Tool):
    """Tool to search knowledge base with tenant and access filtering."""

    def __init__(self, store: KnowledgeStore):
        self.store = store
        self._channel = "cli"
        self._chat_id = "direct"
        self._sender_id = ""
        self._session_key = "cli:direct"
        self._tenant_id = "default"
        self._team_ids: list[str] = []

    def set_context(
        self,
        channel: str,
        chat_id: str,
        sender_id: str = "",
        session_key: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set caller context for permission-aware retrieval."""
        self._channel = channel
        self._chat_id = chat_id
        self._sender_id = sender_id
        self._session_key = session_key or f"{channel}:{chat_id}"
        metadata = metadata or {}
        self._tenant_id = str(metadata.get("tenant_id") or "default")
        self._team_ids = _parse_team_ids(metadata.get("team_ids"))

    @property
    def name(self) -> str:
        return "kb_search"

    @property
    def description(self) -> str:
        return (
            "Search enterprise knowledge base with tenant/permission filtering. "
            "Returns results with source citations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Knowledge query"},
                "count": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Result count"},
                "min_score": {"type": "integer", "minimum": 1, "description": "Minimum token overlap score"},
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        count: int = 5,
        min_score: int = 1,
        **kwargs: Any,
    ) -> str:
        limit = max(1, min(count, 10))
        rows = self.store.search(
            query=query,
            tenant_id=self._tenant_id,
            user_id=self._sender_id,
            team_ids=self._team_ids,
            limit=limit,
        )
        rows = [r for r in rows if int(r.get("score", 0)) >= min_score]
        if not rows:
            return (
                "No relevant internal knowledge found for this query. "
                "Please ask a narrower question or use web_search for external info."
            )

        out: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, 1):
            out.append(
                {
                    "rank": idx,
                    "score": row["score"],
                    "doc_id": row["doc_id"],
                    "source": row["source"],
                    "updated_at": row["updated_at"],
                    "snippet": row["content"][:600],
                    "citation": f"[{idx}] {row['source']} (doc: {row['doc_id']})",
                }
            )
        return json.dumps(
            {
                "query": query,
                "tenant_id": self._tenant_id,
                "session_key": self._session_key,
                "results": out,
            },
            ensure_ascii=False,
            indent=2,
        )

