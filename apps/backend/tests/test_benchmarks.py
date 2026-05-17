"""
Benchmark suite — measures performance of core RAG and agent components.

Covers:
  - Chunker throughput at various document sizes
  - Planner parse speed (ReAct output parsing)
  - Token estimation and batch planning (embedding pre-flight)
  - Extractor: CSV and Excel text extraction
  - Overlap application on large chunk lists

Run with:
    pytest tests/test_benchmarks.py --benchmark-only
    pytest tests/test_benchmarks.py --benchmark-only --benchmark-sort=mean
    pytest tests/test_benchmarks.py --benchmark-save=baseline

Compare runs:
    pytest-benchmark compare baseline
"""

from __future__ import annotations

import io
import random

import pytest
from packages.agents.planner import Planner
from packages.agents.tool_registry import ToolRegistry
from packages.rag.chunker import Chunker
from packages.rag.embeddings import _build_token_aware_batches, _estimate_tokens
from packages.rag.schemas import Document, DocumentMetadata

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_doc(content: str, source: str = "bench.txt") -> Document:
    return Document(
        id="bench-doc",
        content=content,
        metadata=DocumentMetadata(source=source, source_type="text"),
    )


def _lorem(words: int) -> str:
    """Generate deterministic pseudo-text of roughly `words` words."""
    vocab = [
        "the",
        "quick",
        "brown",
        "fox",
        "jumps",
        "over",
        "lazy",
        "dog",
        "revenue",
        "growth",
        "market",
        "analysis",
        "product",
        "customer",
        "service",
        "financial",
        "report",
        "annual",
        "quarterly",
        "data",
        "performance",
        "strategy",
        "investment",
        "technology",
        "platform",
    ]
    rng = random.Random(42)  # fixed seed — deterministic
    sentences = []
    while sum(len(s.split()) for s in sentences) < words:
        length = rng.randint(8, 20)
        sentence = " ".join(rng.choice(vocab) for _ in range(length))
        sentences.append(sentence.capitalize() + ".")
    # Group into paragraphs of 3-5 sentences
    paragraphs = []
    i = 0
    while i < len(sentences):
        size = rng.randint(3, 5)
        paragraphs.append(" ".join(sentences[i : i + size]))
        i += size
    return "\n\n".join(paragraphs)


# Pre-build documents at different sizes so fixture setup isn't counted
_DOC_SMALL = _lorem(500)  # ~3 KB  — typical short article
_DOC_MEDIUM = _lorem(5_000)  # ~30 KB — typical report page
_DOC_LARGE = _lorem(50_000)  # ~300 KB — annual report / long PDF


# ── Chunker benchmarks ────────────────────────────────────────────────────────


class TestChunkerBenchmarks:
    """Measures chunker throughput at different document sizes and chunk configs."""

    def test_chunk_small_doc_default(self, benchmark: pytest.fixture) -> None:
        """Small doc (~3KB) with default settings."""
        chunker = Chunker(max_chunk_size=800, overlap=100)
        doc = _make_doc(_DOC_SMALL)
        result = benchmark(chunker.chunk, doc)
        assert len(result) >= 1

    def test_chunk_medium_doc_default(self, benchmark: pytest.fixture) -> None:
        """Medium doc (~30KB) with default settings."""
        chunker = Chunker(max_chunk_size=800, overlap=100)
        doc = _make_doc(_DOC_MEDIUM)
        result = benchmark(chunker.chunk, doc)
        assert len(result) > 5

    def test_chunk_large_doc_default(self, benchmark: pytest.fixture) -> None:
        """Large doc (~300KB) — simulates a 139-page annual report."""
        chunker = Chunker(max_chunk_size=800, overlap=100)
        doc = _make_doc(_DOC_LARGE)
        result = benchmark(chunker.chunk, doc)
        assert len(result) > 50

    def test_chunk_large_doc_small_chunks(self, benchmark: pytest.fixture) -> None:
        """Large doc with small chunks — maximum granularity."""
        chunker = Chunker(max_chunk_size=400, overlap=50)
        doc = _make_doc(_DOC_LARGE)
        result = benchmark(chunker.chunk, doc)
        assert len(result) > 100

    def test_chunk_large_doc_large_chunks(self, benchmark: pytest.fixture) -> None:
        """Large doc with large chunks — minimum granularity."""
        chunker = Chunker(max_chunk_size=2000, overlap=200)
        doc = _make_doc(_DOC_LARGE)
        result = benchmark(chunker.chunk, doc)
        assert len(result) > 10

    def test_chunk_no_overlap(self, benchmark: pytest.fixture) -> None:
        """Chunking without overlap — baseline for overlap cost."""
        chunker = Chunker(max_chunk_size=800, overlap=1)
        doc = _make_doc(_DOC_MEDIUM)
        result = benchmark(chunker.chunk, doc)
        assert len(result) >= 1

    def test_chunk_single_giant_paragraph(self, benchmark: pytest.fixture) -> None:
        """Worst case: one paragraph with no double newlines — forces sentence splitting."""
        content = " ".join(["word"] * 10_000)  # ~50KB, no paragraph breaks
        chunker = Chunker(max_chunk_size=800, overlap=100)
        doc = _make_doc(content)
        result = benchmark(chunker.chunk, doc)
        assert len(result) > 10


# ── Planner benchmarks ────────────────────────────────────────────────────────


class TestPlannerBenchmarks:
    """Measures ReAct output parsing speed."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        registry = ToolRegistry.with_defaults()
        self.planner = Planner(registry)

    def test_parse_final_answer(self, benchmark: pytest.fixture) -> None:
        """Parse a clean Final Answer response."""
        output = (
            "Thought: I have all the information needed to answer the question.\n"
            "Final Answer: The total revenue for Q4 2024 was $25.7 billion, "
            "representing a 8% year-over-year increase."
        )
        result = benchmark(self.planner.parse, output)
        from packages.agents.schemas import DecisionType

        assert result.decision_type == DecisionType.FINAL_ANSWER

    def test_parse_tool_call_json(self, benchmark: pytest.fixture) -> None:
        """Parse a tool call with valid JSON arguments."""
        output = (
            "Thought: I need to search for the sales data in the documents.\n"
            "Action: read_file\n"
            'Action Input: {"path": "apps/backend/app/main.py"}'
        )
        result = benchmark(self.planner.parse, output)
        from packages.agents.schemas import DecisionType

        assert result.decision_type == DecisionType.TOOL_CALL
        assert result.tool_call is not None
        assert result.tool_call.tool_name == "read_file"

    def test_parse_tool_call_python_dict(self, benchmark: pytest.fixture) -> None:
        """Parse a tool call with Python dict syntax (single quotes) — common LLM output."""
        output = (
            "Thought: Let me look up the document.\n"
            "Action: search_files\n"
            "Action Input: {'pattern': 'annual revenue Tesla 2024', 'file_pattern': '*.py'}"
        )
        result = benchmark(self.planner.parse, output)
        from packages.agents.schemas import DecisionType

        assert result.decision_type == DecisionType.TOOL_CALL
        assert result.tool_call is not None
        assert result.tool_call.tool_name == "search_files"

    def test_parse_long_reasoning(self, benchmark: pytest.fixture) -> None:
        """Parse output with verbose multi-line reasoning."""
        reasoning = " ".join(["I need to think carefully about this."] * 50)
        output = f"Thought: {reasoning}\n" "Final Answer: Based on my analysis, the answer is 42."
        result = benchmark(self.planner.parse, output)
        from packages.agents.schemas import DecisionType

        assert result.decision_type == DecisionType.FINAL_ANSWER

    def test_parse_fallback_unformatted(self, benchmark: pytest.fixture) -> None:
        """Parse completely unformatted LLM output — fallback path."""
        output = _lorem(200)
        result = benchmark(self.planner.parse, output)
        from packages.agents.schemas import DecisionType

        assert result.decision_type == DecisionType.FINAL_ANSWER


# ── Embedding batch planning benchmarks ──────────────────────────────────────


class TestEmbeddingBatchBenchmarks:
    """
    Measures token estimation and batch planning speed.
    These run before any API call — their latency adds to every ingest.
    """

    def test_estimate_tokens_short(self, benchmark: pytest.fixture) -> None:
        """Token estimation for a short chunk (~200 chars)."""
        text = _lorem(40)
        result = benchmark(_estimate_tokens, text)
        assert result > 0

    def test_estimate_tokens_long(self, benchmark: pytest.fixture) -> None:
        """Token estimation for a long chunk (~2000 chars)."""
        text = _lorem(400)
        result = benchmark(_estimate_tokens, text)
        assert result > 0

    def test_batch_planning_small(self, benchmark: pytest.fixture) -> None:
        """Batch planning for a small document (10 chunks)."""
        chunker = Chunker(max_chunk_size=800, overlap=100)
        chunks = chunker.chunk(_make_doc(_DOC_SMALL))
        texts = [c.text for c in chunks]
        result = benchmark(_build_token_aware_batches, texts)
        assert len(result) >= 1

    def test_batch_planning_medium(self, benchmark: pytest.fixture) -> None:
        """Batch planning for a medium document (~50 chunks)."""
        chunker = Chunker(max_chunk_size=800, overlap=100)
        chunks = chunker.chunk(_make_doc(_DOC_MEDIUM))
        texts = [c.text for c in chunks]
        result = benchmark(_build_token_aware_batches, texts)
        assert len(result) >= 1

    def test_batch_planning_large(self, benchmark: pytest.fixture) -> None:
        """Batch planning for a large document (~400 chunks) — annual report scale."""
        chunker = Chunker(max_chunk_size=800, overlap=100)
        chunks = chunker.chunk(_make_doc(_DOC_LARGE))
        texts = [c.text for c in chunks]
        result = benchmark(_build_token_aware_batches, texts)
        # Should split into multiple batches
        assert len(result) >= 2

    def test_batch_planning_respects_token_limit(self, benchmark: pytest.fixture) -> None:
        """Verify no batch exceeds the token limit."""
        from packages.rag.embeddings import _MAX_TOKENS_PER_BATCH

        chunker = Chunker(max_chunk_size=800, overlap=100)
        chunks = chunker.chunk(_make_doc(_DOC_LARGE))
        texts = [c.text for c in chunks]

        def plan_and_verify() -> list:
            batches = _build_token_aware_batches(texts)
            for batch in batches:
                total = sum(_estimate_tokens(t) for t in batch)
                assert total <= _MAX_TOKENS_PER_BATCH
            return batches

        result = benchmark(plan_and_verify)
        assert len(result) >= 1


# ── Extractor benchmarks ──────────────────────────────────────────────────────


class TestExtractorBenchmarks:
    """Measures file extraction speed for CSV and Excel formats."""

    def _make_csv_bytes(self, rows: int) -> bytes:
        """Generate a CSV with `rows` data rows."""
        lines = ["Project,Task,Assignee,Start,Days,End,Progress"]
        rng = random.Random(42)
        names = ["Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona"]
        tasks = ["Research", "Development", "Testing", "Review", "Deployment", "Planning"]
        for i in range(rows):
            lines.append(
                f"Project{i % 5},{rng.choice(tasks)},{rng.choice(names)},"
                f"2024-01-{(i % 28) + 1:02d},{rng.randint(5, 30)},"
                f"2024-02-{(i % 28) + 1:02d},{rng.randint(0, 100)}%"
            )
        return "\n".join(lines).encode("utf-8")

    def _make_xlsx_bytes(self, rows: int) -> bytes:
        """Generate an Excel workbook with `rows` data rows."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"
        ws.append(["Project", "Task", "Assignee", "Start", "Days", "End", "Progress"])
        rng = random.Random(42)
        names = ["Alice", "Bob", "Charlie", "Diana", "Ethan"]
        tasks = ["Research", "Development", "Testing", "Review", "Deployment"]
        for i in range(rows):
            ws.append(
                [
                    f"Project{i % 5}",
                    rng.choice(tasks),
                    rng.choice(names),
                    f"2024-01-{(i % 28) + 1:02d}",
                    rng.randint(5, 30),
                    f"2024-02-{(i % 28) + 1:02d}",
                    f"{rng.randint(0, 100)}%",
                ]
            )
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_extract_csv_small(self, benchmark: pytest.fixture) -> None:
        """Extract a small CSV (50 rows)."""
        from packages.rag.extractor import extract_text

        data = self._make_csv_bytes(50)
        result = benchmark(extract_text, data, "data.csv")
        assert "Project" in result
        assert len(result) > 100

    def test_extract_csv_large(self, benchmark: pytest.fixture) -> None:
        """Extract a large CSV (1000 rows)."""
        from packages.rag.extractor import extract_text

        data = self._make_csv_bytes(1000)
        result = benchmark(extract_text, data, "data.csv")
        assert "Project" in result

    def test_extract_excel_small(self, benchmark: pytest.fixture) -> None:
        """Extract a small Excel workbook (50 rows)."""
        from packages.rag.extractor import extract_text

        data = self._make_xlsx_bytes(50)
        result = benchmark(extract_text, data, "data.xlsx")
        assert "Project" in result

    def test_extract_excel_large(self, benchmark: pytest.fixture) -> None:
        """Extract a large Excel workbook (500 rows)."""
        from packages.rag.extractor import extract_text

        data = self._make_xlsx_bytes(500)
        result = benchmark(extract_text, data, "data.xlsx")
        assert "Project" in result
