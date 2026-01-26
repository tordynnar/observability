#!/usr/bin/env python
import logging
import uuid

import grpc
from opentelemetry import trace

import echo_pb2
import echo_pb2_grpc
from telemetry import ServiceTelemetry, create_service_telemetry, setup_global_telemetry


def do_echo(
    stub: echo_pb2_grpc.EchoStub,
    service: ServiceTelemetry,
    message: str,
) -> None:
    """Make an Echo RPC call with its own trace ID."""
    trace_uuid = uuid.uuid4()
    trace_id = trace_uuid.hex
    service.id_generator.set_next_trace_id(trace_uuid)

    print(f"\n--- Echo: {message} ---")
    print(f"Jaeger: http://localhost:16686/trace/{trace_id}")
    print(
        f"Kibana: http://localhost:5601/app/discover#/?_g=(filters:!(),refreshInterval:(pause:!t,value:60000),time:(from:now-15m,to:now))&_a=(columns:!(message,log.level,service.name),filters:!(),query:(language:kuery,query:'trace.id:\"{trace_id}\"'))"
    )

    with service.tracer.start_as_current_span("echo-request") as span:
        span.add_event("Preparing request", {"message": message})

        service.logger.info("Sending echo request", extra={"request.message": message})
        responses = stub.Echo(echo_pb2.EchoRequest(message=message))

        for i, response in enumerate(responses, 1):
            span.add_event(
                "Response received",
                {
                    "copy": i,
                    "response.message": response.message,
                    "response.length": len(response.message),
                },
            )

            service.logger.info(
                "Received echo response",
                extra={
                    "copy": i,
                    "response.message": response.message,
                    "response.length": len(response.message),
                },
            )
            print(f"Response {i}: {response.message}")

            # Cancel after receiving the first response
            responses.close()
            span.add_event("Cancelled after first response")
            break


def main() -> None:
    # Set up global telemetry infrastructure first
    setup_global_telemetry()

    # Create two services with different names
    service1 = create_service_telemetry("echo-client-1")
    service2 = create_service_telemetry("echo-client-2")

    with grpc.insecure_channel("localhost:50051") as channel:
        stub = echo_pb2_grpc.EchoStub(channel)

        # Two separate Echo calls, each from a different service
        do_echo(stub, service1, "Hello, World!")
        do_echo(stub, service2, "Goodbye, World!")


if __name__ == "__main__":
    main()
