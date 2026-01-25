#!/usr/bin/env python
import logging
import uuid

import grpc
from opentelemetry import trace

import echo_pb2
import echo_pb2_grpc
from telemetry import SettableIdGenerator, setup_telemetry

logger = logging.getLogger(__name__)


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
    id_generator = setup_telemetry("echo-client")
    tracer = trace.get_tracer(__name__)

    with grpc.insecure_channel("localhost:50051") as channel:
        stub = echo_pb2_grpc.EchoStub(channel)

        # Two separate Echo calls, each with their own trace ID
        do_echo(stub, tracer, id_generator, "Hello, World!")
        do_echo(stub, tracer, id_generator, "Goodbye, World!")


if __name__ == "__main__":
    main()
