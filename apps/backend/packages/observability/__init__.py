"""
packages.observability — tracing and observability for the agent runtime.

Lazy imports — importable without Langfuse installed.

Public surface:
    from packages.observability.tracer import AgentTracer, NoOpTracer
    from packages.observability.otel import configure_otel, instrument_fastapi
    from packages.observability.evaluation import AgentEvaluator, evaluate_rag_retrieval
"""
