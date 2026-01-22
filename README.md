# OpenTelemetry Observability Stack

A complete observability stack using OpenTelemetry, Jaeger, Elasticsearch, and Kibana with automatic trace-to-logs correlation.

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│ Echo Client │────▶│  OTel Collector │────▶│   Jaeger    │ (traces)
│ Echo Server │     │   (port 4317)   │     │ (port 16686)│
└─────────────┘     └────────┬────────┘     └─────────────┘
                             │
                             ▼
                    ┌─────────────────┐     ┌─────────────┐
                    │ Elasticsearch   │◀───▶│   Kibana    │ (logs)
                    │  (port 9200)    │     │ (port 5601) │
                    └─────────────────┘     └─────────────┘
```

## Components

| Service | Port | Purpose |
|---------|------|---------|
| OTel Collector | 4317 | Receives OTLP/gRPC telemetry |
| Jaeger | 16686 | Trace visualization |
| Elasticsearch | 9200 | Log storage |
| Kibana | 5601 | Log visualization |

## Quick Start

### 1. Start the infrastructure

```bash
docker-compose up -d
```

### 2. Set up Python environment

```bash
uv venv
source .venv/bin/activate
uv pip install grpcio grpcio-tools opentelemetry-api opentelemetry-sdk \
    opentelemetry-exporter-otlp-proto-grpc opentelemetry-instrumentation-grpc \
    mypy-protobuf
```

### 3. Generate protobuf code

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
    --mypy_out=. --mypy_grpc_out=. echo.proto
```

### 4. Create Kibana data view (required for log viewing)

```bash
./setup-kibana.sh
```

Or manually via the API:
```bash
curl -X POST "http://localhost:5601/api/data_views/data_view" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{
    "data_view": {
      "title": "logs",
      "name": "logs",
      "timeFieldName": "@timestamp"
    }
  }'
```

### 5. Run the echo server and client

```bash
# Terminal 1: Start the server
python echo_server.py

# Terminal 2: Run the client
python echo_client.py
```

The client outputs direct links to view the trace and logs:
```
Jaeger: http://localhost:16686/trace/<trace-id>
Kibana: http://localhost:5601/app/discover#/?...trace.id:"<trace-id>"...
Response: Hello, World!
```

## Trace-to-Logs Correlation

### How it works

1. **Trace ID injection**: The Python client generates a UUID as the trace ID and injects it into the OpenTelemetry context
2. **Automatic correlation**: The OTel logging handler automatically includes `trace.id` and `span.id` in all log records
3. **Elasticsearch indexing**: Logs are indexed with ECS (Elastic Common Schema) mapping
4. **Jaeger external links**: Configured to link to Kibana filtered by trace ID

### Jaeger UI Configuration

The `jaeger-ui-config.json` file configures an external link that appears on every trace:

```json
{
  "linkPatterns": [
    {
      "type": "traces",
      "url": "http://localhost:5601/app/discover#/?_g=...&_a=(query:(query:'trace.id:\"#{traceID}\"'))",
      "text": "View Logs in Kibana"
    }
  ]
}
```

Key points:
- `type: "traces"` - Links appear on the trace page (not span-level)
- `#{traceID}` - Template variable replaced with the actual trace ID
- The URL pre-filters Kibana Discover to show only logs for that trace

### OTel Collector Configuration

The collector receives both traces and logs, routing them to different backends:

```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/jaeger]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [elasticsearch]
```

The Elasticsearch exporter uses ECS mapping mode:
```yaml
exporters:
  elasticsearch:
    endpoints: ["http://elasticsearch:9200"]
    logs_index: logs
    mapping:
      mode: ecs
```

## Manual Kibana Data View Setup

If you don't use the setup script, you must create a data view manually:

1. Open Kibana at http://localhost:5601
2. Click "Create data view"
3. Enter:
   - Name: `logs`
   - Index pattern: `logs`
   - Timestamp field: `@timestamp`
4. Click "Save data view to Kibana"

Without a data view, clicking "View Logs in Kibana" from Jaeger will show a setup prompt instead of logs.

## Log Fields in Elasticsearch

Logs are indexed with these fields (ECS format):

| Field | Description |
|-------|-------------|
| `@timestamp` | Log timestamp |
| `message` | Log message |
| `log.level` | Log level (INFO, ERROR, etc.) |
| `trace.id` | OpenTelemetry trace ID |
| `span.id` | OpenTelemetry span ID |
| `service.name` | Service name (echo-client, echo-service) |
| `code.file.path` | Source file path |
| `code.function.name` | Function name |
| `code.line.number` | Line number |

## Troubleshooting

### Logs not appearing in Elasticsearch

Check the OTel Collector logs:
```bash
docker logs otel-collector
```

Common issues:
- `index_not_found_exception`: Add `mapping.mode: ecs` to the elasticsearch exporter config
- Connection refused: Ensure Elasticsearch is healthy before starting the collector

### Trace not found in Jaeger

Jaeger uses in-memory storage by default. Traces are lost when Jaeger restarts. For persistence, configure Jaeger with a storage backend.

### Kibana shows "Create data view" prompt

Run the setup script or create the data view manually. The data view must exist before Kibana can query the logs index.

## File Structure

```
.
├── docker-compose.yml          # Infrastructure services
├── otel-collector-config.yaml  # OTel Collector configuration
├── jaeger-ui-config.json       # Jaeger external links config
├── echo.proto                   # gRPC service definition
├── echo_server.py              # Python gRPC server with tracing/logging
├── echo_client.py              # Python gRPC client with tracing/logging
├── setup-kibana.sh             # Script to create Kibana data view
└── README.md
```
