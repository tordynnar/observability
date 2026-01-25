# Docker Compose Update - January 2025

This document describes the changes made to update all Docker images to their latest versions.

## Version Changes

| Service | Previous Version | New Version |
|---------|-----------------|-------------|
| OpenTelemetry Collector Contrib | `latest` | `0.144.0` |
| Jaeger | `jaegertracing/all-in-one:latest` | `jaegertracing/jaeger:2.14.1` |
| Elasticsearch | `8.17.0` | `9.2.4` |
| Kibana | `8.17.0` | `9.2.4` |

## Breaking Changes and Required Modifications

### Jaeger v2 Migration

Jaeger v2 is a complete rewrite based on the OpenTelemetry Collector framework. This required significant configuration changes:

1. **Image Change**: The image changed from `jaegertracing/all-in-one` to `jaegertracing/jaeger`

2. **Configuration Format**: Jaeger v2 no longer uses environment variables for configuration. It requires a YAML configuration file following the OpenTelemetry Collector format.

3. **New Configuration File**: Created `jaeger-config.yaml` with:
   - OTLP receiver for trace ingestion (gRPC on port 4317, HTTP on port 4318)
   - Elasticsearch storage backend configuration
   - Jaeger Query extension for the UI
   - Batch processor for performance

4. **Removed Environment Variables**:
   - `COLLECTOR_OTLP_ENABLED` - now configured in YAML
   - `SPAN_STORAGE_TYPE` - now configured in YAML
   - `ES_SERVER_URLS` - now configured in YAML
   - `QUERY_UI_CONFIG` - now configured in YAML as `ui.config_file`

5. **Removed Port**: Port `14268` (Jaeger HTTP collector) is no longer exposed as traces are now received via OTLP

6. **Volume Mounts**: Updated to mount both config files:
   ```yaml
   volumes:
     - ./jaeger-config.yaml:/etc/jaeger/config.yaml:ro
     - ./jaeger-ui-config.json:/etc/jaeger/jaeger-ui-config.json:ro
   ```

### Elasticsearch 9 Migration

Elasticsearch 9.x is a major version upgrade from 8.x:

1. **Data Volume**: The Elasticsearch data volume must be removed when upgrading from 8.x to 9.x as they are not compatible. Run `docker compose down -v` before starting the new version.

2. **No Configuration Changes Required**: The basic configuration options (`discovery.type=single-node`, `xpack.security.enabled=false`, `ES_JAVA_OPTS`) remain compatible.

3. **Jaeger Compatibility**: Jaeger v2 automatically detects Elasticsearch 9 and uses the appropriate API version. Logs show: `Elasticsearch detected {"version": 9}`

### Kibana 9 Migration

Kibana version must match Elasticsearch version. Updated from 8.17.0 to 9.2.4.

**Data View Setup Required**: The default "All logs" data view in Kibana 9 uses index pattern `logs-*-*,logs-*,filebeat-*` which doesn't match our `logs` index. A custom data view must be created to view the OpenTelemetry logs.

#### Option 1: Create via Script (Recommended)

Run this command after Kibana is running:

```bash
curl -X POST "http://localhost:5601/api/data_views/data_view" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"data_view":{"title":"logs","name":"OTel Logs","timeFieldName":"@timestamp"}}'
```

This creates a data view named "OTel Logs" that matches the `logs` index with `@timestamp` as the time field.

To verify it was created:
```bash
curl -s "http://localhost:5601/api/data_views" -H "kbn-xsrf: true" | python3 -m json.tool
```

#### Option 2: Create via Kibana UI

1. Open Kibana at http://localhost:5601

2. Dismiss any security notifications that appear (click "Dismiss")

3. Navigate to **Stack Management**:
   - Click the hamburger menu (☰) in the top left
   - Scroll down and click "Stack Management" under the Management section
   - Or go directly to: http://localhost:5601/app/management

4. Click **Data Views** under the "Kibana" section in the left sidebar
   - Or go directly to: http://localhost:5601/app/management/kibana/dataViews

5. Click the **"Create data view"** button

6. Fill in the form:
   - **Name**: `OTel Logs`
   - **Index pattern**: `logs`
   - The panel on the right should show "Your index pattern matches 1 source" with the `logs` index listed
   - **Timestamp field**: Select `@timestamp` from the dropdown (this enables time-based filtering)

7. Click **"Save data view to Kibana"**

#### Using the Data View

1. Navigate to **Discover**:
   - Click the hamburger menu (☰) in the top left
   - Click "Discover" under the Analytics section
   - Or go directly to: http://localhost:5601/app/discover

2. Select the data view:
   - Click the data view dropdown (shows "All logs" or another data view name)
   - Select **"OTel Logs"** from the list

3. Adjust the time range if needed:
   - Click "Last 15 minutes" in the top right
   - Select an appropriate time range that includes when you ran the echo client

4. You should now see log documents with fields like:
   - `message` - The log message
   - `service.name` - Either "echo-client" or "echo-service"
   - `trace.id` - The trace ID for correlation with Jaeger
   - `span.id` - The span ID
   - `log.level` - The log level (INFO, etc.)

## New Files

### jaeger-config.yaml

New Jaeger v2 configuration file:

```yaml
service:
  extensions: [jaeger_storage, jaeger_query, healthcheckv2]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [jaeger_storage_exporter]
  telemetry:
    resource:
      service.name: jaeger
    logs:
      level: info

extensions:
  healthcheckv2:
    use_v2: true
    http:

  jaeger_query:
    storage:
      traces: es_main
    ui:
      config_file: /etc/jaeger/jaeger-ui-config.json

  jaeger_storage:
    backends:
      es_main:
        elasticsearch:
          server_urls:
            - http://elasticsearch:9200
          indices:
            index_prefix: "jaeger"
            spans:
              date_layout: "2006-01-02"
              rollover_frequency: "day"
              shards: 1
              replicas: 0
            services:
              date_layout: "2006-01-02"
              rollover_frequency: "day"
              shards: 1
              replicas: 0
            dependencies:
              date_layout: "2006-01-02"
              rollover_frequency: "day"
              shards: 1
              replicas: 0
            sampling:
              date_layout: "2006-01-02"
              rollover_frequency: "day"
              shards: 1
              replicas: 0

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  jaeger_storage_exporter:
    trace_storage: es_main
```

## Upgrade Instructions

1. Stop and remove existing containers and volumes:
   ```bash
   docker compose down -v
   ```

2. Pull new images and start:
   ```bash
   docker compose up -d
   ```

3. Verify all services are healthy:
   ```bash
   docker compose ps
   ```

4. Create Kibana data view for logs:
   ```bash
   curl -X POST "http://localhost:5601/api/data_views/data_view" \
     -H "kbn-xsrf: true" \
     -H "Content-Type: application/json" \
     -d '{"data_view":{"title":"logs","name":"OTel Logs","timeFieldName":"@timestamp"}}'
   ```
   Or create manually via UI at http://localhost:5601/app/management/kibana/dataViews

## Verification

### Testing the Stack

Run the echo server and client to generate traces and logs:

```bash
# Terminal 1: Start the server
source .venv/bin/activate
python echo_server.py

# Terminal 2: Run the client
source .venv/bin/activate
python echo_client.py
```

The client outputs URLs for viewing the trace in Jaeger and logs in Kibana.

### Expected Results

**Jaeger UI** (http://localhost:16686):
- Traces visible with 3 spans per request:
  - `echo-client: echo-request` (parent span)
  - `echo-client: /echo.Echo/Echo` (client gRPC call)
  - `echo-service: /echo.Echo/Echo` (server gRPC call)
- "View Logs in Kibana" link available on each trace

**Elasticsearch Indices**:
```bash
curl -s "http://localhost:9200/_cat/indices?v" | grep -E "jaeger|logs"
```
Expected output:
- `jaeger-jaeger-span-YYYY-MM-DD` - trace spans
- `jaeger-jaeger-service-YYYY-MM-DD` - service registry
- `logs` - application logs

**Kibana Discover** (http://localhost:5601/app/discover):
- 4 log documents per echo request/response cycle
- Fields include: `message`, `service.name`, `trace.id`, `span.id`, `log.level`
- Logs correlated with traces via `trace.id`

### Verified Log Messages

| Timestamp | Service | Message |
|-----------|---------|---------|
| T+0ms | echo-client | Sending echo request |
| T+18ms | echo-service | Received echo request: Hello, World! |
| T+21ms | echo-service | Sending echo response: Hello, World! |
| T+24ms | echo-client | Received echo response |

## Service Endpoints

| Service | URL |
|---------|-----|
| Jaeger UI | http://localhost:16686 |
| Kibana | http://localhost:5601 |
| Elasticsearch | http://localhost:9200 |
| OTLP gRPC (traces/logs) | localhost:4317 |

## Troubleshooting

### Jaeger not connecting to Elasticsearch

Check Jaeger logs for Elasticsearch detection:
```bash
docker compose logs jaeger | grep -i elasticsearch
```
Should show: `Elasticsearch detected {"version": 9}`

### Logs not appearing in Kibana

1. Verify the `logs` index exists:
   ```bash
   curl -s "http://localhost:9200/_cat/indices/logs?v"
   ```

2. Ensure the "OTel Logs" data view is created in Kibana with index pattern `logs`

3. Adjust the time range in Kibana Discover to include when logs were generated

### Traces not appearing in Jaeger

1. Check OpenTelemetry Collector logs:
   ```bash
   docker compose logs otel-collector
   ```

2. Verify Jaeger is receiving traces:
   ```bash
   docker compose logs jaeger | grep -i "trace\|span"
   ```

## Sources

- [OpenTelemetry Collector Contrib Releases](https://github.com/open-telemetry/opentelemetry-collector-contrib/releases)
- [Jaeger Download Page](https://www.jaegertracing.io/download/)
- [Jaeger v2 Configuration Documentation](https://www.jaegertracing.io/docs/2.4/deployment/configuration/)
- [Jaeger v2 Elasticsearch Configuration Example](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/config-elasticsearch.yaml)
- [Elasticsearch Docker Registry](https://www.docker.elastic.co/r/elasticsearch)
- [Kibana Docker Registry](https://www.docker.elastic.co/r/kibana)
