"""RAG retrieval with TF-IDF default and optional embeddings."""

from __future__ import annotations

import math

from models.rag_schemas import RagChunk, RetrievedEvidence
from models.schemas import BusinessCase
from services.embedding_client import EmbeddingClient


def build_query_from_case(case: BusinessCase, transcript: str | None = None) -> str:
    parts = [
        f"업종: {case.industry or '미확인'}",
        f"지역: {case.region or '미확인'}",
        f"업력: {case.business_months or '미확인'}개월",
        f"매출상황: {case.revenue_trend or '미확인'}",
        f"연매출: {case.annual_revenue or '미확인'}",
        f"자금용도: {case.funding_purpose or '미확인'}",
        f"필요금액: {case.required_amount or '미확인'}",
        f"기존대출: {case.existing_loan or '미확인'}",
        f"기존보증: {case.existing_guarantee or '미확인'}",
        f"신용: {case.credit_band or case.credit_score or '미확인'}",
        f"체납: {case.tax_arrears or '미확인'}",
        f"사업상태: {case.business_status or '미확인'}",
    ]
    if case.raw_consultation:
        parts.append(f"상담원문: {case.raw_consultation[:500]}")
    if transcript or case.transcript:
        parts.append(f"transcript: {(transcript or case.transcript or '')[:500]}")
    return " ".join(parts)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


def _tfidf_search(query: str, chunks: list[RagChunk], top_k: int) -> list[RetrievedEvidence]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    texts = [c.text for c in chunks]
    if not texts:
        return []
    vectorizer = TfidfVectorizer(max_features=5000)
    matrix = vectorizer.fit_transform(texts + [query])
    q_vec = matrix[-1]
    doc_matrix = matrix[:-1]
    scores = cosine_similarity(q_vec, doc_matrix)[0]
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    results: list[RetrievedEvidence] = []
    for idx, score in ranked:
        c = chunks[idx]
        meta = c.metadata
        results.append(
            RetrievedEvidence(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                title=c.title,
                text=c.text,
                score=float(score),
                source_name=meta.get("source_name"),
                source_url=meta.get("source_url"),
                source_date=meta.get("source_date"),
                is_sample_data=meta.get("is_sample_data", True),
            )
        )
    return results


def retrieve_relevant_chunks(
    case: BusinessCase,
    chunks: list[RagChunk],
    top_k: int = 8,
    transcript: str | None = None,
) -> list[RetrievedEvidence]:
    if not chunks:
        return []
    query = build_query_from_case(case, transcript)
    client = EmbeddingClient()
    if client.mode() == "openai":
        try:
            texts = [c.text for c in chunks]
            embeddings = client.embed_texts(texts)
            q_emb = client.embed_texts([query])[0]
            scored = [(i, _cosine_sim(q_emb, emb)) for i, emb in enumerate(embeddings)]
            scored.sort(key=lambda x: x[1], reverse=True)
            results = []
            for idx, score in scored[:top_k]:
                c = chunks[idx]
                meta = c.metadata
                results.append(
                    RetrievedEvidence(
                        chunk_id=c.chunk_id, doc_id=c.doc_id, title=c.title, text=c.text,
                        score=float(score), source_name=meta.get("source_name"),
                        source_url=meta.get("source_url"), source_date=meta.get("source_date"),
                        is_sample_data=meta.get("is_sample_data", True),
                    )
                )
            return results
        except Exception:
            pass
    return _tfidf_search(query, chunks, top_k)
