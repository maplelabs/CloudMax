# Booking Diagnostics Demo

This directory contains optional booking-specific diagnostic tools. The core
MCP server remains domain-neutral; its generic Kafka consumer-lag and
PostgreSQL health tools do not load these booking tools.

## Included

- Booking presence and time-range queries.
- Booking processing checks across PostgreSQL, Kafka, and consumer offsets.
- Booking DLQ searches.
- A demo MCP server extension, direct Kafka diagnostic client, and DLQ runbook.

## Run the demo MCP server

Install the requirements in `diagnostics/mcp-server/requirements.txt`
and configure the PostgreSQL/Kafka environment variables required by
`diagnostics/mcp-server/src/config/settings.py`. From the repository
root, start the demo with:

```bash
cd diagnostics/mcp-server
MTLS_ENABLED=false python ../../demos/booking-demo/booking_demo/server.py --host 127.0.0.1 --port 8080
```

This starts the generic core tools plus the booking-demo tools. Run
`MTLS_ENABLED=false python src/main.py --host 127.0.0.1 --port 8080` instead
for the core-only server.

## Run the direct Kafka client

From the repository root, with PostgreSQL and Kafka configured and reachable:

```bash
cd diagnostics/mcp-server
python ../../demos/booking-demo/booking_demo/client.py check-processed --booking-id 6
python ../../demos/booking-demo/booking_demo/client.py check-dlq --booking-id 6
python ../../demos/booking-demo/booking_demo/client.py all --booking-id 6
```

The sample client defaults to `booking-post-processing-group` and
`booking-events`; pass `--consumer-group` and `--topic` to match your demo
environment. The DLQ command derives the topic by appending `-dlq`.

The detailed example workflow is in [DLQ_ALERT_RUNBOOK.md](DLQ_ALERT_RUNBOOK.md).
