#!/usr/bin/env python
import logging
from concurrent import futures

import grpc
from opentelemetry import trace

import echo_pb2
import echo_pb2_grpc
from telemetry import setup_telemetry

logger = logging.getLogger(__name__)


class EchoServicer(echo_pb2_grpc.EchoServicer):
    def Echo(
        self,
        request: echo_pb2.EchoRequest,
        context: grpc.ServicerContext,
    ) -> echo_pb2.EchoResponse:
        # Get the current span created by gRPC instrumentation
        span = trace.get_current_span()

        span.add_event("Request received", {"message": request.message})
        logger.info(f"Received echo request: {request.message}")

        response = echo_pb2.EchoResponse(message=request.message)

        span.add_event("Response prepared", {"message": response.message})
        logger.info(f"Sending echo response: {response.message}")

        return response


def serve() -> None:
    setup_telemetry("echo-service")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    echo_pb2_grpc.add_EchoServicer_to_server(EchoServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    print("Echo server listening on port 50051")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
