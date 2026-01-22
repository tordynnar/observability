#!/usr/bin/env python
import logging
import random
import uuid

import grpc
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

import echo_pb2
import echo_pb2_grpc

logger = logging.getLogger(__name__)


def setup_telemetry() -> None:
    resource = Resource.create({"service.name": "echo-client"})

    # Use SimpleSpanProcessor/SimpleLogRecordProcessor to export telemetry immediately.
    # BatchSpanProcessor is more efficient but buffers data, which can be lost if the
    # process exits before the buffer is flushed. For short-lived processes or demos,
    # SimpleSpanProcessor ensures all telemetry is exported before the process exits.

    # Tracing
    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
    trace_provider.add_span_processor(SimpleSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    GrpcInstrumentorClient().instrument()

    # Logging
    log_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint="localhost:4317", insecure=True)
    log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    set_logger_provider(log_provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=log_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def new_trace_context() -> tuple[uuid.UUID, Context]:
    """Create a new trace context with a UUID as the trace ID."""
    trace_uuid = uuid.uuid4()
    ctx = trace.set_span_in_context(
        NonRecordingSpan(
            SpanContext(
                trace_id=trace_uuid.int,
                span_id=random.getrandbits(64),
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
        )
    )
    return trace_uuid, ctx


def main() -> None:
    setup_telemetry()
    tracer = trace.get_tracer(__name__)

    trace_uuid, ctx = new_trace_context()
    trace_id = trace_uuid.hex
    print(f"Jaeger: http://localhost:16686/trace/{trace_id}")
    print(f"Kibana: http://localhost:5601/app/discover#/?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-1h,to:now))&_a=(columns:!(message,log.level),filters:!(),query:(language:kuery,query:'trace.id:\"{trace_id}\"'))")

    with grpc.insecure_channel("localhost:50051") as channel:
        stub = echo_pb2_grpc.EchoStub(channel)
        with tracer.start_as_current_span("echo-request", context=ctx) as span:
            # Span events are embedded in the trace and visible in Jaeger
            span.add_event("Preparing request", {"message": "Hello, World!"})

            logger.info("Sending echo request")
            response = stub.Echo(echo_pb2.EchoRequest(message="Hello, World!"))

            span.add_event("Response received", {
                "response.message": response.message,
                "response.length": len(response.message),
            })

            logger.info(f"Received echo response: {response.message}")
            print(f"Response: {response.message}")


if __name__ == "__main__":
    main()
