#!/usr/bin/env python
"""Shared OpenTelemetry setup for tracing and logging."""

import logging
import random
import uuid

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator


class SettableIdGenerator(IdGenerator):
    """ID generator that allows setting a custom trace ID for the next root span."""

    def __init__(self) -> None:
        self._next_trace_id: int | None = None

    def set_next_trace_id(self, trace_uuid: uuid.UUID) -> None:
        """Set the trace ID to use for the next root span."""
        self._next_trace_id = trace_uuid.int

    def generate_trace_id(self) -> int:
        if self._next_trace_id is not None:
            trace_id = self._next_trace_id
            self._next_trace_id = None
            return trace_id
        return random.getrandbits(128)

    def generate_span_id(self) -> int:
        return random.getrandbits(64)


def setup_telemetry(service_name: str) -> SettableIdGenerator:
    """Set up OpenTelemetry tracing and logging.

    Args:
        service_name: The name of the service for resource identification.

    Returns:
        The ID generator, which can be used to set custom trace IDs for root spans.
    """
    resource = Resource.create({"service.name": service_name})

    # Use SimpleSpanProcessor/SimpleLogRecordProcessor to export telemetry immediately.
    # BatchSpanProcessor is more efficient but buffers data, which can be lost if the
    # process exits before the buffer is flushed. For short-lived processes or demos,
    # SimpleSpanProcessor ensures all telemetry is exported before the process exits.

    # Tracing - use settable ID generator to control trace IDs for root spans
    id_generator = SettableIdGenerator()
    trace_provider = TracerProvider(
        resource=resource,
        id_generator=id_generator,
    )
    trace_exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
    trace_provider.add_span_processor(SimpleSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    # Instrument both gRPC client and server
    GrpcInstrumentorClient().instrument()
    GrpcInstrumentorServer().instrument()

    # Logging
    log_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint="localhost:4317", insecure=True)
    log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    set_logger_provider(log_provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=log_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    return id_generator
