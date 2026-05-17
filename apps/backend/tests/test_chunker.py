"""
Chunker unit tests — deterministic, no external dependencies.
"""

import pytest
from packages.rag.chunker import Chunker
from packages.rag.schemas import Document, DocumentMetadata


def _make_doc(content: str, source: str = "test.py") -> Document:
    return Document(
        id="doc-1",
        content=content,
        metadata=DocumentMetadata(source=source, source_type="file"),
    )


def test_short_document_produces_one_chunk() -> None:
    chunker = Chunker(max_chunk_size=1500, overlap=200)
    doc = _make_doc("Hello world. This is a short document.")
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert "Hello world" in chunks[0].text


def test_chunk_index_is_sequential() -> None:
    chunker = Chunker(max_chunk_size=100, overlap=20)
    content = "\n\n".join([f"Paragraph {i}. " * 5 for i in range(10)])
    doc = _make_doc(content)
    chunks = chunker.chunk(doc)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunks_preserve_document_id() -> None:
    chunker = Chunker(max_chunk_size=100, overlap=20)
    content = "\n\n".join([f"Section {i}. " * 10 for i in range(5)])
    doc = _make_doc(content)
    chunks = chunker.chunk(doc)
    for chunk in chunks:
        assert chunk.document_id == "doc-1"


def test_chunks_preserve_metadata() -> None:
    chunker = Chunker(max_chunk_size=200, overlap=50)
    doc = _make_doc("Some content.\n\nMore content.", source="myfile.py")
    chunks = chunker.chunk(doc)
    for chunk in chunks:
        assert chunk.metadata.source == "myfile.py"
        assert chunk.metadata.source_type == "file"


def test_overlap_is_applied() -> None:
    """The tail of chunk N should appear at the start of chunk N+1."""
    chunker = Chunker(max_chunk_size=100, overlap=30)
    # Create content that will definitely produce multiple chunks
    paragraphs = [f"This is paragraph number {i} with some content." for i in range(20)]
    content = "\n\n".join(paragraphs)
    doc = _make_doc(content)
    chunks = chunker.chunk(doc)

    if len(chunks) > 1:
        # The second chunk should contain some text from the first
        first_tail = chunks[0].text[-30:]
        assert first_tail in chunks[1].text
        # At least some overlap should be present
        assert len(chunks[1].text) > 0


def test_empty_document_produces_one_chunk() -> None:
    chunker = Chunker()
    doc = _make_doc("")
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1


def test_large_paragraph_is_split() -> None:
    """A single paragraph larger than max_chunk_size must be split."""
    chunker = Chunker(max_chunk_size=100, overlap=20)
    # Single paragraph, no double newlines, 500 chars
    content = "word " * 100  # ~500 chars
    doc = _make_doc(content)
    chunks = chunker.chunk(doc)
    assert len(chunks) > 1
    for chunk in chunks:
        # Each chunk should be within reasonable bounds
        assert len(chunk.text) <= 200  # max + overlap


def test_invalid_overlap_raises() -> None:
    with pytest.raises(ValueError, match="overlap"):
        Chunker(max_chunk_size=100, overlap=100)


def test_chunk_ids_are_unique() -> None:
    chunker = Chunker(max_chunk_size=100, overlap=20)
    content = "\n\n".join([f"Para {i}. " * 10 for i in range(10)])
    doc = _make_doc(content)
    chunks = chunker.chunk(doc)
    ids = [chunk.id for chunk in chunks]
    assert len(ids) == len(set(ids))
