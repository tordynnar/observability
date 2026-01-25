#!/usr/bin/env python
import logging
import random
import uuid

import grpc
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator

import echo_pb2
import echo_pb2_grpc

logger = logging.getLogger(__name__)


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


def setup_telemetry() -> SettableIdGenerator:
    resource = Resource.create({"service.name": "echo-client"})

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
    GrpcInstrumentorClient().instrument()

    # Logging
    log_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint="localhost:4317", insecure=True)
    log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    set_logger_provider(log_provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=log_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    return id_generator


def do_echo(
    stub: echo_pb2_grpc.EchoStub,
    tracer: trace.Tracer,
    id_generator: SettableIdGenerator,
    message: str,
) -> None:
    """Make an Echo RPC call with its own trace ID."""
    trace_uuid = uuid.uuid4()
    trace_id = trace_uuid.hex
    id_generator.set_next_trace_id(trace_uuid)

    print(f"\n--- Echo: {message} ---")
    print(f"Jaeger: http://localhost:16686/trace/{trace_id}")
    print(f"Kibana: http://localhost:5601/app/discover#/?_g=(filters:!(),refreshInterval:(pause:!t,value:60000),time:(from:now-15m,to:now))&_a=(columns:!(message,log.level,service.name),filters:!(),query:(language:kuery,query:'trace.id:\"{trace_id}\"'))")

    with tracer.start_as_current_span("echo-request") as span:
        span.add_event("Preparing request", {"message": message})

        logger.info("Sending echo request", extra={"request.message": message})
        response = stub.Echo(echo_pb2.EchoRequest(message=message))

        span.add_event("Response received", {
            "response.message": response.message,
            "response.length": len(response.message),
        })

        logger.info("Received echo response", extra={
            "response.message": response.message,
            "response.length": len(response.message),
        })
        print(f"Response: {response.message}")


def main() -> None:
    id_generator = setup_telemetry()
    tracer = trace.get_tracer(__name__)

    with grpc.insecure_channel("localhost:50051") as channel:
        stub = echo_pb2_grpc.EchoStub(channel)

        # Two separate Echo calls, each with their own trace ID
        do_echo(stub, tracer, id_generator, "Hello, World!")
        do_echo(stub, tracer, id_generator, "Goodbye, World!")


if __name__ == "__main__":
    main()
