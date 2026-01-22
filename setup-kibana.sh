#!/bin/bash
# Setup script to create Kibana data view for logs

set -e

KIBANA_URL="${KIBANA_URL:-http://localhost:5601}"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "Waiting for Kibana to be ready..."

for i in $(seq 1 $MAX_RETRIES); do
    if curl -s "${KIBANA_URL}/api/status" | grep -q '"level":"available"'; then
        echo "Kibana is ready!"
        break
    fi
    if [ $i -eq $MAX_RETRIES ]; then
        echo "Error: Kibana not ready after ${MAX_RETRIES} attempts"
        exit 1
    fi
    echo "Waiting for Kibana... (attempt $i/$MAX_RETRIES)"
    sleep $RETRY_INTERVAL
done

echo "Checking for existing 'logs' data view..."

EXISTING=$(curl -s "${KIBANA_URL}/api/data_views" -H "kbn-xsrf: true" | grep -c '"name":"logs"' || true)

if [ "$EXISTING" -gt 0 ]; then
    echo "Data view 'logs' already exists, skipping creation"
    exit 0
fi

echo "Waiting for logs index to exist in Elasticsearch..."

ES_URL="${ES_URL:-http://localhost:9200}"

for i in $(seq 1 $MAX_RETRIES); do
    if curl -s "${ES_URL}/_cat/indices" | grep -q "^[^ ]* *[^ ]* *logs "; then
        echo "Logs index found!"
        break
    fi
    if [ $i -eq $MAX_RETRIES ]; then
        echo "Warning: logs index not found, creating data view anyway"
        break
    fi
    echo "Waiting for logs index... (attempt $i/$MAX_RETRIES)"
    sleep $RETRY_INTERVAL
done

echo "Creating 'logs' data view..."

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${KIBANA_URL}/api/data_views/data_view" \
    -H "kbn-xsrf: true" \
    -H "Content-Type: application/json" \
    -d '{
        "data_view": {
            "title": "logs",
            "name": "logs",
            "timeFieldName": "@timestamp"
        }
    }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ]; then
    echo "Successfully created 'logs' data view"
    echo "Kibana is ready to view logs at: ${KIBANA_URL}/app/discover"
else
    echo "Error creating data view (HTTP $HTTP_CODE):"
    echo "$BODY"
    exit 1
fi
