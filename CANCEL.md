# gRPC Streaming Cancellation in Python

This document explains how cancellation works when a client stops consuming a gRPC server-streaming response in Python, particularly when using OpenTelemetry instrumentation.

## The Cancellation Chain

When a client calls `close()` on a streaming response, the cancellation propagates through several layers:

```
responses.close()
    → OpenTelemetry generator closes
    → yield from drops reference to _MultiThreadedRendezvous
    → Garbage collection triggers __del__()
    → __del__() calls self._call.cancel()
    → Server's context.is_active() returns False
```

## Step-by-Step Breakdown

### 1. Client Code

```python
responses = stub.Echo(echo_pb2.EchoRequest(message="Hello"))

for i, response in enumerate(responses, 1):
    print(f"Response {i}: {response.message}")

    # Cancel after first response
    responses.close()
    break
```

### 2. OpenTelemetry Instrumentation Layer

The OpenTelemetry gRPC client instrumentation wraps streaming responses in a generator. From `opentelemetry/instrumentation/grpc/_client.py:195-220`:

```python
def _intercept_server_stream(
    self, request_or_iterator, metadata, client_info, invoker
):
    # ...
    with self._start_span(client_info.full_method) as span:
        # ...
        try:
            yield from invoker(request_or_iterator, metadata)
        except grpc.RpcError as err:
            # ...
```

The key is `yield from invoker(...)`. When `close()` is called on this generator, Python's `yield from` machinery drops the reference to the inner iterator.

### 3. The Raw gRPC Response Object

Without instrumentation, `stub.Echo()` returns a `grpc._channel._MultiThreadedRendezvous` object:

```python
>>> responses = stub.Echo(request)
>>> type(responses)
<class 'grpc._channel._MultiThreadedRendezvous'>
>>> hasattr(responses, 'cancel')
True
```

This object has a `cancel()` method, but the OpenTelemetry wrapper hides it behind a generator that only exposes `close()`.

### 4. Garbage Collection Triggers Cancellation

When the generator's reference to `_MultiThreadedRendezvous` is dropped, Python's garbage collector calls `__del__()`. From `grpc/_channel.py:555-565`:

```python
def __del__(self) -> None:
    with self._state.condition:
        if self._state.code is None:
            self._state.code = grpc.StatusCode.CANCELLED
            self._state.details = "Cancelled upon garbage collection!"
            self._state.cancelled = True
            self._call.cancel(
                _common.STATUS_CODE_TO_CYGRPC_STATUS_CODE[self._state.code],
                self._state.details,
            )
            self._state.condition.notify_all()
```

This is the actual cancellation point - `self._call.cancel()` sends the cancellation to the server via the C extension (`cygrpc`).

### 5. Server Detects Cancellation

The server can check if the client has cancelled using `context.is_active()`:

```python
class EchoServicer(echo_pb2_grpc.EchoServicer):
    def Echo(self, request, context):
        for i in range(3):
            if not context.is_active():
                print("Client cancelled, stopping")
                break

            yield echo_pb2.EchoResponse(message=request.message)
            time.sleep(1)
```

## Key Insights

1. **`close()` does NOT directly call `cancel()`** - It triggers garbage collection which then cancels.

2. **The cancellation message is literally "Cancelled upon garbage collection!"** - This is hardcoded in gRPC's `_Rendezvous.__del__()`.

3. **OpenTelemetry hides the `cancel()` method** - The instrumentation wraps the response in a generator, which doesn't expose `cancel()`. Only `close()` is available.

4. **Servers must explicitly check for cancellation** - Use `context.is_active()` in loops to stop processing when the client disconnects.

5. **Cancellation happens immediately, not at script exit** - The `__del__()` destructor is called as soon as `close()` drops the reference, not when the Python script terminates.

## Timing Verification

To confirm that cancellation happens immediately (not at script exit), we can add timestamps and a delay after `close()`:

```python
print(f"[{timestamp()}] CLIENT: Calling close()")
responses.close()
print(f"[{timestamp()}] CLIENT: close() returned")
print(f"[{timestamp()}] CLIENT: Sleeping 3 seconds...")
time.sleep(3)
print(f"[{timestamp()}] CLIENT: Done sleeping, exiting")
```

Output with timestamps:

```
[11:50:42] CLIENT: Calling close()
[11:50:42] CLIENT: close() returned
[11:50:42] CLIENT: Sleeping 3 seconds...
[11:50:43] SERVER: Client cancelled, stopping   ← Server stops here
[11:50:45] CLIENT: Done sleeping, exiting       ← Script exits 2 seconds later
```

The server detects cancellation at **11:50:43** (after its 1-second sleep completes), while the client script doesn't exit until **11:50:45**. This proves that `__del__()` is triggered immediately when `close()` drops the reference to `_MultiThreadedRendezvous`, not when the script terminates.

## Raw gRPC vs OpenTelemetry Instrumented

| Aspect | Raw gRPC | With OpenTelemetry |
|--------|----------|-------------------|
| Response type | `_MultiThreadedRendezvous` | `generator` |
| Cancel method | `responses.cancel()` | `responses.close()` |
| Mechanism | Direct cancel call | GC triggers `__del__()` |

## Comparison: With vs Without Cancellation Check

### Without check (server keeps running):
```python
def Echo(self, request, context):
    for i in range(3):
        yield echo_pb2.EchoResponse(message=request.message)
        time.sleep(1)  # Continues sleeping even after client cancels
```

### With check (server stops promptly):
```python
def Echo(self, request, context):
    for i in range(3):
        if not context.is_active():
            break
        yield echo_pb2.EchoResponse(message=request.message)
        if i < 2:
            time.sleep(1)
```

## File References

- **OpenTelemetry client interceptor**: `opentelemetry/instrumentation/grpc/_client.py`
  - `_intercept_server_stream()` at line 195

- **gRPC Rendezvous class**: `grpc/_channel.py`
  - `_Rendezvous.__del__()` at line 555
  - `_Rendezvous.cancel()` at line 508

- **Example client**: `echo_client.py`
- **Example server**: `echo_server.py`
