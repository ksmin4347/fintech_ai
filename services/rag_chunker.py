"""Document chunking for RAG."""

from __future__ import annotations

import hashlib

from models.rag_schemas import PolicyDocument, RagChunk

MIN_CHUNK_LEN = 100


def _stable_chunk_id(doc_id: str, index: int, text: str) -> str:
    h = hashlib.md5(f"{doc_id}:{index}:{text[:50]}".encode()).hexdigest()[:12]
    return f"{doc_id}_chunk_{index}_{h}"


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return parts if parts else [text]


def _split_by_size(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def chunk_documents(
    documents: list[PolicyDocument],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[RagChunk]:
    all_chunks: list[RagChunk] = []
    for doc in documents:
        paragraphs = _split_paragraphs(doc.raw_text)
        merged: list[str] = []
        buf = ""
        for para in paragraphs:
            if len(para) < MIN_CHUNK_LEN and buf:
                buf += "\n\n" + para
            elif len(para) < MIN_CHUNK_LEN:
                buf = para
            else:
                if buf:
                    merged.append(buf)
                    buf = ""
                merged.append(para)
        if buf:
            merged.append(buf)

        idx = 0
        for block in merged:
            sub_chunks = _split_by_size(block, chunk_size, chunk_overlap)
            for sub in sub_chunks:
                all_chunks.append(
                    RagChunk(
                        chunk_id=_stable_chunk_id(doc.doc_id, idx, sub),
                        doc_id=doc.doc_id,
                        title=doc.title,
                        text=sub,
                        metadata={
                            "institution": doc.institution,
                            "source_name": doc.source_name,
                            "source_url": doc.source_url,
                            "source_date": doc.source_date,
                            "is_sample_data": doc.is_sample_data,
                        },
                    )
                )
                idx += 1
    return all_chunks
