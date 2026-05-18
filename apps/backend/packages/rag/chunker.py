"""
Document chunker — splits documents into overlapping text chunks.

Strategy:
- Split on paragraph boundaries first (double newlines)
- If a paragraph exceeds max_chunk_size, split on sentence boundaries
- Overlap between chunks preserves context across boundaries
- Metadata is preserved on every chunk

Design decisions:
- No external NLP libraries — pure Python string operations
- Deterministic output for the same input (testable)
- Chunk size measured in characters (not tokens) for simplicity
  Phase 3 will add token-aware chunking for better LLM context management

Typical settings:
- max_chunk_size=1500 chars ≈ 300-400 tokens (well within embedding limits)
- overlap=200 chars ≈ 40 tokens (enough context continuity)
"""

from __future__ import annotations

import re
import uuid

from packages.rag.schemas import Chunk, Document, DocumentMetadata


class Chunker:
    """
    Splits a Document into overlapping Chunk objects.

    Usage:
        chunker = Chunker(max_chunk_size=1500, overlap=200)
        chunks = chunker.chunk(document)
    """

    def __init__(self, max_chunk_size: int = 1500, overlap: int = 200) -> None:
        if overlap >= max_chunk_size:
            raise ValueError("overlap must be less than max_chunk_size")
        self._max_chunk_size = max_chunk_size
        self._overlap = overlap

    def chunk(self, document: Document) -> list[Chunk]:
        """Split a document into chunks. Returns at least one chunk."""
        raw_chunks = self._split_text(document.content)
        chunks: list[Chunk] = []

        for index, text in enumerate(raw_chunks):
            text = text.strip()
            if not text:
                continue
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document.id,
                    text=text,
                    chunk_index=index,
                    metadata=document.metadata,
                )
            )

        # Edge case: empty document produces no chunks — return one empty chunk
        if not chunks:
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document.id,
                    text=document.content.strip() or "(empty)",
                    chunk_index=0,
                    metadata=document.metadata,
                )
            )

        return chunks

    def _split_text(self, text: str) -> list[str]:
        """
        Split text into chunks respecting paragraph and sentence boundaries.

        Algorithm:
        1. Split on paragraph boundaries (2+ newlines)
        2. Merge small paragraphs until max_chunk_size is reached
        3. Split oversized paragraphs on sentence boundaries
        4. Apply overlap between consecutive chunks
        """
        # Step 1: Split into paragraphs
        paragraphs = re.split(r"\n{2,}", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return [text] if text.strip() else []

        # Step 2: Build chunks by merging paragraphs
        raw_chunks: list[str] = []
        current_chunk = ""

        for paragraph in paragraphs:
            # If this paragraph alone exceeds max size, split it further
            if len(paragraph) > self._max_chunk_size:
                # Flush current chunk first
                if current_chunk:
                    raw_chunks.append(current_chunk)
                    current_chunk = ""
                # Split the large paragraph on sentence boundaries
                sentence_chunks = self._split_on_sentences(paragraph)
                raw_chunks.extend(sentence_chunks)
                continue

            # Would adding this paragraph exceed the limit?
            separator = "\n\n" if current_chunk else ""
            candidate = current_chunk + separator + paragraph

            if len(candidate) <= self._max_chunk_size:
                current_chunk = candidate
            else:
                # Flush and start new chunk
                if current_chunk:
                    raw_chunks.append(current_chunk)
                current_chunk = paragraph

        if current_chunk:
            raw_chunks.append(current_chunk)

        # Step 3: Apply overlap
        return self._apply_overlap(raw_chunks)

    def _split_on_sentences(self, text: str) -> list[str]:
        """Split a large paragraph on sentence boundaries."""
        # Simple sentence splitter — handles . ! ? followed by space/newline
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            candidate = (current + " " + sentence).strip() if current else sentence
            if len(candidate) <= self._max_chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If a single sentence exceeds max size, hard-split it
                if len(sentence) > self._max_chunk_size:
                    for start in range(0, len(sentence), self._max_chunk_size - self._overlap):
                        chunks.append(sentence[start : start + self._max_chunk_size])
                    current = ""
                else:
                    current = sentence

        if current:
            chunks.append(current)

        return chunks

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """
        Add overlap between consecutive chunks.

        Each chunk (except the first) prepends the last `overlap` characters
        of the previous chunk. This preserves context across boundaries.
        """
        if len(chunks) <= 1 or self._overlap == 0:
            return chunks

        overlapped: list[str] = [chunks[0]]
        for index in range(1, len(chunks)):
            previous = chunks[index - 1]
            tail = previous[-self._overlap :] if len(previous) > self._overlap else previous
            overlapped.append(tail + "\n\n" + chunks[index])

        return overlapped
