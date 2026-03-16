"""
rag.py — Knowledge retrieval engine.

Contextualises incidents using a vector knowledge base.
Embeds expert runbook strings using FakeEmbeddings (stub) and
indexes them in an in-memory FAISS index (cosine similarity).

UPGRADE: swap FakeEmbeddings -> OpenAIEmbeddings(api_key=...)
UPGRADE: replace FAISS -> ChromaDB or Pinecone for persistence
"""

from __future__ import annotations

import logging
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings
from langchain_core.documents import Document

logger = logging.getLogger("sre_rag")
logger.setLevel(logging.INFO)


SEED_RUNBOOKS = [
    "High CPU usage on service: Root cause is typically a runaway loop. Runbook: Restart the affected pods, and if the issue persists across restarts, scale replicas horizontally by adding 3 pods to shed load.",
    "Memory leak detected: RSS grows linearly. Runbook: Often due to unreleased DB connection pools. Temporary fix is to restart the pod. Long-term fix requires rolling back the deployment if a recent rollout initiated the leak.",
    "Latency spike on API gateway: Often caused by downstream service dependencies timing out. Runbook: Reroute traffic away from the slow downstream replica or flush the upstream cache to force fresh connections.",
    "Pod crash loop backoff (CrashLoopBackOff): Service fails to start. Runbook: Revert the deployment to the last known stable revision immediately. This typically indicates a missing environment variable or bad configuration in the manifest.",
    "Disk saturation on logging node: Elasticsearch/fluentd nodes running out of space. Runbook: Flush cache / delete old indices. If critical, scale volume limits or restart log ingestion pods to reset buffers.",
    "Network partition / unreachable nodes: Service cannot connect to DB or Redis. Runbook: This is a network-level event. No code actions (restart/rollback) will fix this. Reroute traffic to a healthy availability zone.",
    "DB connection exhaustion: PostgreSQL hitting max_connections. Runbook: Flush the connection pool cache on the API layer. Alternatively, restart the API pods to forcefully sever zombie connections.",
    "Deployment rollback procedure: When any service exhibits a severe degradation (CRITICAL severity) within 1 hour of a deployment rollout, automatically execute a rollback_deployment action to restore service stability."
]


class KnowledgeBase:
    """FAISS-backed vector store for expert SRE Runbooks."""

    def __init__(self, embedding_dim: int = 384) -> None:
        logger.info("KnowledgeBase | Initialising FakeEmbeddings and FAISS index")
        self._embeddings = FakeEmbeddings(size=embedding_dim)
        
        docs = [
            Document(page_content=text, metadata={"guide_idx": i})
            for i, text in enumerate(SEED_RUNBOOKS)
        ]
        self._store = FAISS.from_documents(docs, self._embeddings)
        logger.info(f"KnowledgeBase | Seeded {len(docs)} expert runbooks into index.")

    def query(self, anomaly_summary: str, k: int = 3) -> list[str]:
        """
        Embed the query, run k-NN search, and return the top-k guide texts.
        """
        logger.info(f"KnowledgeBase | Querying for nearest {k} guides for anomaly: '{anomaly_summary}'")
        docs = self._store.similarity_search(anomaly_summary, k=k)
        results = [doc.page_content for doc in docs]
        logger.info(f"KnowledgeBase | Found {len(results)} matching guides.")
        return results
