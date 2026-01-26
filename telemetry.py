#!/usr/bin/env python
"""Shared OpenTelemetry setup for tracing and logging."""

import logging
import random
import uuid
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
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


@dataclass
class ServiceTelemetry:
    """Container for service-specific telemetry components."""

    tracer: trace.Tracer
    logger: logging.Logger
    id_generator: SettableIdGenerator


def create_service_telemetry(service_name: str) -> ServiceTelemetry:
    """Create telemetry components for a specific service.

    This allows multiple services to coexist in the same process, each with
    their own tracer and logger that report the correct service name.

    Args:
        service_name: The name of the service for resource identification.

    Returns:
        ServiceTelemetry containing the tracer, logger, and ID generator.
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

    # Get a tracer from this specific provider (not the global one)
    tracer = trace_provider.get_tracer(service_name)

    # Logging - create a service-specific logger
    log_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint="localhost:4317", insecure=True)
    log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))

    # Create a dedicated logger for this service
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    handler = LoggingHandler(level=logging.INFO, logger_provider=log_provider)
    logger.addHandler(handler)

    return ServiceTelemetry(tracer=tracer, logger=logger, id_generator=id_generator)


def setup_global_telemetry() -> None:
    """Set up global telemetry infrastructure (propagation, gRPC instrumentation).

    Call this once at process startup before creating service-specific telemetry.
    """
    # Set up W3C TraceContext propagator explicitly
    set_global_textmap(TraceContextTextMapPropagator())

    # Instrument gRPC - these work with context propagation
    GrpcInstrumentorClient().instrument()
    GrpcInstrumentorServer().instrument()


def setup_telemetry(service_name: str) -> SettableIdGenerator:
    """Set up OpenTelemetry tracing and logging for a single-service process.

    This is the simple API for processes that only have one service identity.
    For multi-service processes, use setup_global_telemetry() and
    create_service_telemetry() instead.

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

    # Set up W3C TraceContext propagator explicitly
    set_global_textmap(TraceContextTextMapPropagator())

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
