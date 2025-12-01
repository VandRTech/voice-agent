import argparse
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

from chromadb import PersistentClient
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_kb")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    if len(text) <= chunk_size:
        return [text.strip()]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk.strip())
        if end >= len(text):
            break
        start = max(end - overlap, 0)
    return [c for c in chunks if c]


def load_jsonl(path: Path) -> List[Dict]:
    docs = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def load_markdown(path: Path) -> List[Dict]:
    text = path.read_text(encoding="utf-8").strip()
    return [
        {
            "id": path.stem,
            "title": path.stem.replace("_", " ").title(),
            "text": text,
            "meta": {"source": str(path)},
        }
    ]


def load_documents(source_dir: Path) -> List[Dict]:
    docs: List[Dict] = []
    for file in source_dir.glob("**/*"):
        if file.is_dir():
            continue
        if file.suffix.lower() == ".jsonl":
            docs.extend(load_jsonl(file))
        elif file.suffix.lower() in {".md", ".txt"}:
            docs.extend(load_markdown(file))
    return docs


def embed_chunks(chunks: List[str], model: str) -> List[List[float]]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        raise EnvironmentError("OPENAI_API_KEY env var is required for embeddings.")

    embeddings = []
    for chunk in chunks:
        response = client.embeddings.create(model=model, input=chunk)
        embeddings.append(response.data[0].embedding)
    return embeddings


def prepare_chunks(docs: List[Dict], chunk_size: int, overlap: int, tenant_id: str) -> Tuple[List[str], List[str], List[Dict]]:
    ids: List[str] = []
    texts: List[str] = []
    metas: List[Dict] = []

    for doc in docs:
        base_id = doc.get("id") or doc.get("title")
        text = doc.get("text", "")
        metadata = doc.get("meta", {}).copy()
        metadata["tenant_id"] = tenant_id
        metadata["title"] = doc.get("title")

        for idx, chunk in enumerate(chunk_text(text, chunk_size, overlap)):
            chunk_id = f"{base_id}_{idx}"
            ids.append(chunk_id)
            texts.append(chunk)
            metas.append(metadata.copy())

    return ids, texts, metas


def seed_collection(source_dir: Path, chroma_path: Path, collection_name: str, chunk_size: int, overlap: int, embedding_model: str, tenant_id: str):
    docs = load_documents(source_dir)
    if not docs:
        raise ValueError(f"No documents found under {source_dir}")

    ids, texts, metas = prepare_chunks(docs, chunk_size, overlap, tenant_id)
    logger.info("Loaded %s documents, creating %s chunks", len(docs), len(texts))

    embeddings = embed_chunks(texts, embedding_model)
    client = PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(name=collection_name, metadata={"tenant_id": tenant_id})

    collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metas)
    logger.info("Seeded collection '%s' with %s chunks", collection_name, len(ids))


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Seed clinic knowledge base into Chroma.")
    parser.add_argument("--source", default="data/kb", help="Directory containing KB files (jsonl/md)")
    parser.add_argument("--collection", default="clinic_kb_demo", help="Chroma collection name")
    parser.add_argument("--chroma-path", default="data/chroma", help="Directory for Chroma persistence")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--tenant-id", default="demo")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    return parser


def main():
    args = build_arg_parser().parse_args()
    source_dir = Path(args.source)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory {source_dir} not found")

    chroma_path = Path(args.chroma_path)
    chroma_path.mkdir(parents=True, exist_ok=True)

    seed_collection(
        source_dir=source_dir,
        chroma_path=chroma_path,
        collection_name=args.collection,
        chunk_size=args.chunk_size,
        overlap=args.chunk_overlap,
        embedding_model=args.embedding_model,
        tenant_id=args.tenant_id,
    )


if __name__ == "__main__":
    main()

