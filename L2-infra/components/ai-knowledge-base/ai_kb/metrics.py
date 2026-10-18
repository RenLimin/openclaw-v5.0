"""
Prometheus metrics collector for AI Knowledge Base
Exposes counters/gauges for key operations
"""
from typing import Optional
from prometheus_client import Counter, Gauge, Histogram

# Metrics definitions
KB_QUERY_COUNT = Counter(
    "aikb_query_total",
    "Total number of KB queries",
    ["domain_code"]
)
KB_QUERY_SUCCESS = Counter(
    "aikb_query_success_total",
    "Total number of successful KB queries (with results)",
    ["domain_code"]
)
KB_QUERY_LATENCY = Histogram(
    "aikb_query_latency_seconds",
    "Latency of KB queries in seconds",
    ["domain_code"]
)
KB_INGEST_COUNT = Counter(
    "aikb_ingest_documents_total",
    "Total number of documents ingested",
    ["domain_code"]
)
KB_INGEST_SUCCESS = Counter(
    "aikb_ingest_documents_success",
    "Total number of successful document ingestions",
    ["domain_code"]
)
KB_INGEST_LATENCY = Histogram(
    "aikb_ingest_latency_seconds",
    "Latency of document ingestion in seconds",
    ["domain_code"]
)
KB_DOCUMENTS = Gauge(
    "aikb_documents_total",
    "Total number of documents in KB",
    ["domain_code"]
)
KB_ENTITIES = Gauge(
    "aikb_entities_total",
    "Total number of entities in KB",
    ["domain_code"]
)
KB_CHUNKS = Gauge(
    "aikb_chunks_total",
    "Total number of chunks in KB",
    ["domain_code"]
)
KB_FEEDBACK_RECEIVED = Counter(
    "aikb_feedback_total",
    "Total number of feedback received",
    ["domain_code", "type"]
)
KB_CACHE_HITS = Counter(
    "aikb_cache_hits_total",
    "Total number of query cache hits",
    ["domain_code"]
)
KB_CACHE_MISSES = Counter(
    "aikb_cache_misses_total",
    "Total number of query cache misses",
    ["domain_code"]
)


class MetricsCollector:
    """
    Wrap Prometheus metrics for easier use in KB service.
    If prometheus_client is not installed, all operations are no-ops.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        try:
            import prometheus_client
        except ImportError:
            self.enabled = False

    def inc_query(self, domain_code: str, success: bool, latency: float):
        """Increment query metrics"""
        if not self.enabled:
            return
        KB_QUERY_COUNT.labels(domain_code).inc()
        KB_QUERY_LATENCY.labels(domain_code).observe(latency)
        if success:
            KB_QUERY_SUCCESS.labels(domain_code).inc()

    def inc_ingest(self, domain_code: str, success: bool, latency: float):
        """Increment ingestion metrics"""
        if not self.enabled:
            return
        KB_INGEST_COUNT.labels(domain_code).inc()
        KB_INGEST_LATENCY.labels(domain_code).observe(latency)
        if success:
            KB_INGEST_SUCCESS.labels(domain_code).inc()

    def set_counts(self, domain_code: str, entities: int, docs: int, chunks: int):
        """Set the total counts for gauges"""
        if not self.enabled:
            return
        KB_ENTITIES.labels(domain_code).set(entities)
        KB_DOCUMENTS.labels(domain_code).set(docs)
        KB_CHUNKS.labels(domain_code).set(chunks)

    def inc_feedback(self, domain_code: str, feedback_type: str):
        """Increment feedback counter"""
        if not self.enabled:
            return
        KB_FEEDBACK_RECEIVED.labels(domain_code, feedback_type).inc()

    def inc_cache(self, domain_code: str, hit: bool):
        """Increment cache hit/miss"""
        if not self.enabled:
            return
        if hit:
            KB_CACHE_HITS.labels(domain_code).inc()
        else:
            KB_CACHE_MISSES.labels(domain_code).inc()
