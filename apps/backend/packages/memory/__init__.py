"""
packages.memory — memory systems for the agent runtime.

Lazy imports — importable without Redis or LLM dependencies.

Public surface:
    from packages.memory.manager import MemoryManager
    from packages.memory.short_term import ShortTermMemory
    from packages.memory.long_term import LongTermMemory
    from packages.memory.summarizer import MemorySummarizer
    from packages.memory.vector_memory import VectorMemory
    from packages.memory.schemas import MemoryContext, ConversationTurn, MemoryEntry
"""
