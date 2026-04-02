import json

import pytest

from nanobot.agent.tools.kb import KBIngestTool, KBSearchTool
from nanobot.kb.store import KnowledgeStore


@pytest.mark.asyncio
async def test_kb_ingest_and_search_with_citations(tmp_path) -> None:
    store = KnowledgeStore(workspace=tmp_path)
    ingest = KBIngestTool(store)
    search = KBSearchTool(store)

    result = await ingest.execute(
        doc_id="faq-1",
        content="Nanobot supports Slack and Telegram channels for enterprise teams.",
        source="faq.md",
        tenant_id="acme",
        visibility="public",
        updated_at="2026-04-02T09:00:00",
    )
    assert "KB document upserted" in result

    search.set_context(
        channel="slack",
        chat_id="c1",
        sender_id="u1",
        session_key="slack:c1",
        metadata={"tenant_id": "acme", "team_ids": ["ops"]},
    )
    payload = await search.execute(query="Telegram enterprise teams", count=3)
    data = json.loads(payload)
    assert data["tenant_id"] == "acme"
    assert data["results"][0]["citation"].startswith("[1] faq.md")


@pytest.mark.asyncio
async def test_kb_search_returns_no_answer_fallback(tmp_path) -> None:
    store = KnowledgeStore(workspace=tmp_path)
    search = KBSearchTool(store)
    search.set_context(
        channel="telegram",
        chat_id="1",
        sender_id="u1",
        session_key="telegram:1",
        metadata={"tenant_id": "acme"},
    )
    payload = await search.execute(query="unknown topic")
    assert "No relevant internal knowledge found" in payload

