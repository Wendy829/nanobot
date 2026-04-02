from nanobot.kb.store import KnowledgeStore


def test_upsert_and_search_with_tenant_and_visibility(tmp_path) -> None:
    store = KnowledgeStore(workspace=tmp_path, max_chunk_chars=40)
    store.upsert_document(
        doc_id="doc-public",
        content="Nanobot supports enterprise knowledge retrieval with citations.",
        source="README",
        updated_at="2026-04-02T00:00:00",
        tenant_id="acme",
        visibility="public",
    )
    store.upsert_document(
        doc_id="doc-private",
        content="Private incident runbook for owner u1 only.",
        source="runbook",
        updated_at="2026-04-02T00:00:00",
        tenant_id="acme",
        visibility="private",
        owner_id="u1",
    )
    store.upsert_document(
        doc_id="doc-team",
        content="Team ops guide for blue team members.",
        source="ops",
        updated_at="2026-04-02T00:00:00",
        tenant_id="acme",
        visibility="team",
        team_id="blue",
    )

    public = store.search(query="citations retrieval", tenant_id="acme", user_id="u2", team_ids=[])
    assert any(r["doc_id"] == "doc-public" for r in public)
    assert all(r["doc_id"] != "doc-private" for r in public)

    private = store.search(query="incident runbook", tenant_id="acme", user_id="u1", team_ids=[])
    assert any(r["doc_id"] == "doc-private" for r in private)

    team = store.search(query="ops guide", tenant_id="acme", user_id="u3", team_ids=["blue"])
    assert any(r["doc_id"] == "doc-team" for r in team)

    wrong_tenant = store.search(query="citations", tenant_id="other", user_id="u1", team_ids=["blue"])
    assert wrong_tenant == []


def test_upsert_replaces_old_chunks(tmp_path) -> None:
    store = KnowledgeStore(workspace=tmp_path, max_chunk_chars=20)
    first = store.upsert_document(
        doc_id="doc1",
        content="A " * 50,
        source="s1",
        updated_at="2026-04-02T00:00:00",
    )
    second = store.upsert_document(
        doc_id="doc1",
        content="short content",
        source="s1",
        updated_at="2026-04-02T00:01:00",
    )
    assert first["upserted"] > 1
    assert second["deleted"] == first["upserted"]
    assert second["upserted"] == 1

