#!/usr/bin/env python
import logging
from concurrent import futures

import grpc
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import echo_pb2
import echo_pb2_grpc

logger = logging.getLogger(__name__)


def setup_telemetry() -> None:
    resource = Resource.create({"service.name": "echo-service"})

    # Use SimpleSpanProcessor/SimpleLogRecordProcessor to export telemetry immediately.
    # BatchSpanProcessor is more efficient but buffers data, which can be lost if the
    # process exits before the buffer is flushed. For short-lived processes or demos,
    # SimpleSpanProcessor ensures all telemetry is exported before the process exits.

    # Tracing
    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
    trace_provider.add_span_processor(SimpleSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    GrpcInstrumentorServer().instrument()

    # Logging
    log_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint="localhost:4317", insecure=True)
    log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    set_logger_provider(log_provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=log_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


class EchoServicer(echo_pb2_grpc.EchoServicer):
    def Echo(
        self,
        request: echo_pb2.EchoRequest,
        context: grpc.ServicerContext,
    ) -> echo_pb2.EchoResponse:
        logger.info(f"Received echo request: {request.message}")
        response = echo_pb2.EchoResponse(message=request.message)
        logger.info(f"Sending echo response: {response.message}")
        return response


def serve() -> None:
    setup_telemetry()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    echo_pb2_grpc.add_EchoServicer_to_server(EchoServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    print("Echo server listening on port 50051")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
