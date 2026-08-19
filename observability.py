"""OpenTelemetry helpers for ACTA AI."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False
load_dotenv()


def _is_enabled() -> bool:
    if "pytest" in sys.modules and os.getenv("ACTA_OBSERVABILITY_IN_TESTS", "false").lower() != "true":
        return False
    if os.getenv("ACTA_OBSERVABILITY_ENABLED", "true").lower() in {"0", "false", "no"}:
        return False
    return any(
        os.getenv(name)
        for name in (
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        )
    )


def configure_observability(default_service_name: str) -> bool:
    """Configure OTLP exporters when OpenTelemetry env vars are present."""

    global _configured
    if _configured:
        return True
    if not _is_enabled():
        return False

    os.environ.setdefault("OTEL_SERVICE_NAME", default_service_name)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    service_name = os.getenv("OTEL_SERVICE_NAME", default_service_name)
    environment = os.getenv("ACTA_ENV", "development")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "acta",
            "deployment.environment": environment,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    _configured = True
    return True


def instrument_fastapi_app(app: Any, *, service_name: str = "acta-ai") -> None:
    if configure_observability(service_name):
        FastAPIInstrumentor.instrument_app(app)


def _clean_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    if not attributes:
        return {}
    return {
        key: value
        for key, value in attributes.items()
        if value is not None and isinstance(value, str | int | float | bool)
    }


@contextmanager
def observed_span(name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
    if not _configured:
        yield None
        return

    with trace.get_tracer("acta.ai").start_as_current_span(name) as span:
        for key, value in _clean_attributes(attributes).items():
            span.set_attribute(key, value)
        yield span


@lru_cache(maxsize=1)
def _meter():
    return metrics.get_meter("acta.ai")


@lru_cache(maxsize=1)
def _chat_latency():
    return _meter().create_histogram(
        "acta_ai_chat_latency_ms",
        unit="ms",
        description="Latencia total da rota /chat do ACTA AI.",
    )


@lru_cache(maxsize=1)
def _stage_latency():
    return _meter().create_histogram(
        "acta_ai_pipeline_stage_latency_ms",
        unit="ms",
        description="Latencia das etapas internas da pipeline do ACTA AI.",
    )


@lru_cache(maxsize=1)
def _tool_latency():
    return _meter().create_histogram(
        "acta_ai_mcp_tool_latency_ms",
        unit="ms",
        description="Latencia das chamadas do acta-ai para tools MCP.",
    )


@lru_cache(maxsize=1)
def _tool_calls():
    return _meter().create_counter(
        "acta_ai_mcp_tool_calls_total",
        description="Total de chamadas do acta-ai para tools MCP.",
    )


def record_chat_latency(duration_ms: float, *, status: str) -> None:
    if _configured:
        _chat_latency().record(duration_ms, {"status": status})


def record_pipeline_stage(stage: str, duration_ms: float) -> None:
    if _configured:
        _stage_latency().record(duration_ms, {"stage": stage})


def record_mcp_tool_call(tool_name: str, duration_ms: float, *, status: str, cached: bool) -> None:
    if not _configured:
        return
    attributes = {"tool": tool_name, "status": status, "cached": cached}
    _tool_calls().add(1, attributes)
    _tool_latency().record(duration_ms, attributes)
