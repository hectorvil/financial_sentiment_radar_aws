import streamlit as st
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer


@st.cache_resource
def load_embedder() -> SentenceTransformer:
    # device='cpu' garantiza que Mini-LM no use la GPU
    return SentenceTransformer("all-MiniLM-L6-v2", device="cpu")


class VectorDB:
    def __init__(self, path: str = "chroma_db"):
        self.client = PersistentClient(path)
        self.collection = self.client.get_or_create_collection(
            name="tweets", metadata={"hnsw:space": "cosine"}
        )
        self.embedder = load_embedder()

    # ── helpers internos ────────────────────────────────────────────
    def _filter_new(self, ids, texts, embeds):
        """Filtra doc_ids ya existentes para evitar ValueError de duplicados."""
        existing = set(self.collection.get(ids=ids, include=[])["ids"])
        new_ids, new_txt, new_emb = [], [], []
        for i, t, e in zip(ids, texts, embeds):
            if i not in existing:
                new_ids.append(i)
                new_txt.append(t)
                new_emb.append(e)
        return new_ids, new_txt, new_emb

    # ── API pública ────────────────────────────────────────────────
    def add(self, ids, texts, embeddings=None):
        """Añade documentos deduplicando IDs; calcula embeddings si faltan."""
        if embeddings is None:
            # ───────────────────────────────────────────────────────────────
            # 2) Embeddings en CPU para estabilidad
            embeddings = (
                self.embedder.encode(texts, batch_size=64, device="cpu")
                .tolist()
            )
        ids, texts, embeddings = self._filter_new(ids, texts, embeddings)
        if ids:
            self.collection.add(ids=ids, documents=texts, embeddings=embeddings)

    def query(self, query_text: str, k: int = 30):
        q_emb = self.embedder.encode([query_text]).tolist()
        res = self.collection.query(query_embeddings=q_emb, n_results=k)
        return res["documents"][0]
