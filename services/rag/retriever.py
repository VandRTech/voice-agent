import os
from dataclasses import dataclass
from typing import List

from chromadb import PersistentClient
try:
    from chromadb.errors import InvalidCollectionException
except ImportError:  # chromadb>=1.0 renamed errors
    InvalidCollectionException = Exception
from openai import OpenAI


@dataclass
class RetrievedDocument:
    id: str
    text: str
    score: float
    metadata: dict


class ClinicRetriever:
    def __init__(
        self,
        collection_name: str = "clinic_kb_demo",
        chroma_path: str = "data/chroma",
        embedding_model: str = "text-embedding-3-small",
        tenant_id: str = "demo",
    ):
        self.tenant_id = tenant_id
        self.client = PersistentClient(path=chroma_path)
        self.collection = self._get_or_create_collection(collection_name)
        self.embedding_model = embedding_model
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        if not self.openai_client.api_key:
            raise EnvironmentError("OPENAI_API_KEY env var is required for retrieval.")

    def retrieve(self, query: str, top_k: int = 3, score_threshold: float = 0.7) -> List[RetrievedDocument]:
        if not query.strip():
            return []

        embedding = self._embed_query(query)
        query_results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where={"tenant_id": self.tenant_id},
        )

        documents = query_results.get("documents", [[]])[0]
        ids = query_results.get("ids", [[]])[0]
        metadatas = query_results.get("metadatas", [[]])[0]
        distances = query_results.get("distances")

        results: List[RetrievedDocument] = []
        for idx, text in enumerate(documents):
            doc_id = ids[idx]
            metadata = metadatas[idx] or {}
            distance = distances[0][idx] if distances else None
            score = 1 - distance if distance is not None else 0.0
            if score < score_threshold:
                continue
            results.append(
                RetrievedDocument(
                    id=doc_id,
                    text=text,
                    score=score,
                    metadata=metadata,
                )
            )
        return results

    def _get_or_create_collection(self, name: str):
        try:
            return self.client.get_collection(name=name)
        except InvalidCollectionException:
            return self.client.create_collection(name=name, metadata={"tenant_id": self.tenant_id})

    def _embed_query(self, query: str) -> List[float]:
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=query,
        )
        return response.data[0].embedding


def format_docs_for_prompt(documents: List[RetrievedDocument], max_docs: int = 2) -> str:
    lines: List[str] = []
    for doc in documents[:max_docs]:
        lines.append(f"[DOC id: {doc.id}]")
        lines.append(doc.text.strip())
        lines.append("")
    return "\n".join(lines).strip()

