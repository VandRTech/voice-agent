from chromadb import PersistentClient

from data.kb.seed_kb import seed_collection


def test_seed_collection_creates_chunks(monkeypatch, tmp_path):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    kb_file = kb_dir / "faq.jsonl"
    kb_file.write_text(
        '{"id":"faq_x","title":"Test","text":"Sample text for testing purposes.","meta":{}}\n',
        encoding="utf-8",
    )

    embeddings = [[0.1, 0.2, 0.3]]
    monkeypatch.setattr(
        "data.kb.seed_kb.embed_chunks",
        lambda texts, model: embeddings,
    )

    chroma_dir = tmp_path / "chroma"
    seed_collection(
        source_dir=kb_dir,
        chroma_path=chroma_dir,
        collection_name="test_collection",
        chunk_size=200,
        overlap=0,
        embedding_model="test-model",
        tenant_id="demo",
    )

    client = PersistentClient(path=str(chroma_dir))
    collection = client.get_collection("test_collection")
    stored = collection.get()
    assert stored["ids"], "Collection should store documents"

