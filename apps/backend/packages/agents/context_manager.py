"""
Context Manager — token budget enforcement and context optimization.

The current runtime injects memory context, conversation history, tool results,
and system prompts without any token accounting. Under load this causes:
- Silent context window overflow (Gemini 1.5 Pro: 1M tokens, but costs scale)
- Degraded reasoning quality when context is bloated
- Unpredictable latency as context grows

This module implements:
1. Token budget tracking (approximate, using char-based heuristic)
2. Context truncation strategies (oldest-first, tool-output-first)
3. Tool output size enforcement
4. History window enforcement
5. Context size metrics

Token counting strategy:
- We use 4 chars ≈ 1 token (English text heuristic)
- This is approximate but avoids the overhead of a tokenizer
- Phase 7 will add exact token counting via the Vertex AI tokenize API

Truncation priority (what gets cut first):
1. Old tool observations (least recent, most verbose)
2. Old conversation turns (beyond window)
3. Long tool outputs (truncated to max_tool_output_chars)
4. Memory context (summary preferred over raw turns)

Usage:
    manager = ContextManager(max_tokens=100_000, max_tool_output_chars=8_000)
    messages = manager.prepare_messages(working_messages)
    budget = manager.estimate_tokens(messages)
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Characters per token approximation (English text)
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Approximate token count from character count."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _estimate_message_tokens(message: object) -> int:
    """Estimate tokens for a single message object."""
    content = getattr(message, "content", "") or ""
    # Add ~4 tokens overhead per message for role/formatting
    return _estimate_tokens(content) + 4


class ContextManager:
    """
    Enforces token budgets and truncates context to fit within limits.

    Injected into the runtime to gate every LLM call.
    """

    def __init__(
        self,
        max_tokens: int = 100_000,
        max_tool_output_chars: int = 8_000,
        max_history_messages: int = 50,
    ) -> None:
        self._max_tokens = max_tokens
        self._max_tool_output_chars = max_tool_output_chars
        self._max_history_messages = max_history_messages

    def estimate_tokens(self, messages: list[Any]) -> int:
        """Estimate total token count for a message list."""
        return sum(_estimate_message_tokens(msg) for msg in messages)

    def truncate_tool_output(self, output: str, tool_name: str = "") -> str:
        """
        Truncate a tool output to the configured maximum.

        Adds a truncation notice so the LLM knows the output was cut.
        """
        if len(output) <= self._max_tool_output_chars:
            return output

        truncated = output[: self._max_tool_output_chars]
        notice = (
            f"\n\n[Output truncated at {self._max_tool_output_chars} chars. "
            "Full output available via tool call.]"
        )

        logger.info(
            "tool_output_truncated",
            tool_name=tool_name,
            original_chars=len(output),
            truncated_chars=self._max_tool_output_chars,
        )

        return truncated + notice

    def prepare_messages(self, messages: list[Any], correlation_id: str = "") -> list[Any]:
        """
        Prepare a message list for an LLM call.

        Applies:
        1. History window cap (remove oldest non-system messages)
        2. Token budget enforcement (truncate if over budget)

        Returns a new list — does not mutate the input.
        """
        # Separate system messages from conversation
        system_messages = [m for m in messages if getattr(m, "role", "") == "system"]
        conversation = [m for m in messages if getattr(m, "role", "") != "system"]

        # Apply history window cap
        if len(conversation) > self._max_history_messages:
            dropped = len(conversation) - self._max_history_messages
            conversation = conversation[-self._max_history_messages :]
            logger.info(
                "context_history_truncated",
                dropped_messages=dropped,
                remaining_messages=len(conversation),
                correlation_id=correlation_id,
            )

        prepared = system_messages + conversation
        estimated_tokens = self.estimate_tokens(prepared)

        if estimated_tokens > self._max_tokens:
            prepared = self._truncate_to_budget(system_messages, conversation, correlation_id)
            final_tokens = self.estimate_tokens(prepared)
            logger.warning(
                "context_budget_exceeded",
                estimated_tokens=estimated_tokens,
                max_tokens=self._max_tokens,
                final_tokens=final_tokens,
                correlation_id=correlation_id,
            )
        else:
            logger.debug(
                "context_prepared",
                estimated_tokens=estimated_tokens,
                message_count=len(prepared),
                correlation_id=correlation_id,
            )

        return prepared

    def _truncate_to_budget(
        self,
        system_messages: list[Any],
        conversation: list[Any],
        correlation_id: str,
    ) -> list[Any]:
        """
        Truncate conversation to fit within token budget.

        Strategy: remove oldest conversation messages first,
        always preserving system messages and the most recent exchange.
        """
        # Always keep at least the last 2 messages (most recent user + assistant)
        min_keep = min(2, len(conversation))
        recent = conversation[-min_keep:]
        older = conversation[:-min_keep] if len(conversation) > min_keep else []

        # Remove oldest messages until we're within budget
        while older and self.estimate_tokens(system_messages + older + recent) > self._max_tokens:
            removed = older.pop(0)
            logger.debug(
                "context_message_dropped",
                role=getattr(removed, "role", "unknown"),
                correlation_id=correlation_id,
            )

        return system_messages + older + recent

    def get_budget_status(self, messages: list[Any]) -> dict[str, Any]:
        """Return a dict describing current context budget usage."""
        estimated = self.estimate_tokens(messages)
        return {
            "estimated_tokens": estimated,
            "max_tokens": self._max_tokens,
            "utilization_pct": round(estimated / self._max_tokens * 100, 1),
            "is_over_budget": estimated > self._max_tokens,
            "message_count": len(messages),
        }
