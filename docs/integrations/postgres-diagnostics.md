# Diagnostic MCP Server - PostgreSQL Tools

Core MCP tools for diagnosing PostgreSQL and Kafka infrastructure. The core
server is domain-neutral; booking-specific diagnostics are isolated in
[`demos/booking-demo/`](../../demos/booking-demo/README.md).

## Core Tools

| Tool | Purpose |
|------|---------|
| `health_check` | Check server health |
| `get_consumer_lag_tool` | Get Kafka consumer lag for a consumer group |
| `db_check_access_tool` | Check if PostgreSQL is reachable |
| `db_check_write_locks_tool` | Check for pending write locks |
| `db_check_max_connections_tool` | Check current vs max connections |

---

## Prerequisites

1. **PostgreSQL** running from `hotel-reservation-application`
2. **Kafka** running (for Kafka tools)
3. **Python 3.12+** with virtual environment
4. **psycopg2-binary** and **confluent-kafka** installed

---

## Quick Start

From the repository root, configure PostgreSQL/Kafka settings and install
`diagnostics/mcp-server/requirements.txt`. Start the core server:

```bash
cd diagnostics/mcp-server
MTLS_ENABLED=false python3 -m src.main --host 0.0.0.0
```

In another terminal, from `diagnostics/mcp-server/`, run the
core PostgreSQL checks:

```bash
python3 tests/postgres_diagnostic_client.py all
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HOST MACHINE                            │
│                                                             │
│   ┌─────────────────┐                                       │
│   │   MCP Server    │                                       │
│   │  (Python app)   │───────► localhost:5432 (PostgreSQL)   │
│   │  Port: 8080     │───────► localhost:9092 (Kafka)        │
│   └─────────────────┘              │                        │
│                                    │                        │
│   ┌────────────────────────────────┼───────────────────┐    │
│   │              DOCKER            │                   │    │
│   │                                ▼                   │    │
│   │   ┌─────────────────────────────────┐              │    │
│   │   │      postgres container         │              │    │
│   │   │   (hotel-reservation-app)       │              │    │
│   │   │      port 5432 exposed          │              │    │
│   │   └─────────────────────────────────┘              │    │
│   │   ┌─────────────────────────────────┐              │    │
│   │   │      kafka container            │              │    │
│   │   │      port 9092 exposed          │              │    │
│   │   └─────────────────────────────────┘              │    │
│   └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Why `localhost`?**
- MCP server runs on **host machine** (not in Docker)
- Containers expose ports to host via `ports: "5432:5432"` and `ports: "9092:9092"`
- Host machine accesses containers via `localhost:<port>`

---

## Tool Details

### 1. db_check_access_tool

Checks if PostgreSQL database is reachable by running `SELECT 1`.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `database_url` | string | No | Connection URL (uses settings if not provided) |

**Response:**
```json
{ "db_accessible": true, "error": null }
```

---

### 2. db_check_write_locks_tool

Checks for pending write locks using `pg_locks` system table.

**Parameters:** None

**Response (no locks):**
```json
{ "has_pending_locks": false, "pending_lock_count": 0, "locks": null, "error": null }
```

**Response (with locks):**
```json
{
  "has_pending_locks": true,
  "pending_lock_count": 2,
  "locks": [
    { "pid": 1234, "lock_mode": "ExclusiveLock", "table_name": "sample_table", "granted": false }
  ],
  "error": null
}
```

---

### 3. db_check_max_connections_tool

Checks current active connections vs maximum allowed.

**Parameters:** None

**Response:**
```json
{
  "connection_count": 6,
  "max_connection_limit": 100,
  "max_connections_reached": false,
  "usage_percentage": 6.0,
  "error": null
}
```

---

## Timeout Handling

All tools include **30-second timeout** using `asyncio.wait_for()` to prevent MCP server hanging:

```python
result = await asyncio.wait_for(
    asyncio.to_thread(_sync_function, args),
    timeout=TOOL_TIMEOUT_SECONDS  # 30 seconds
)
```

**Timeout Response:**
```json
{ "error": "Operation timed out after 30 seconds" }
```

---

## Logging

Each tool logs at INFO and ERROR levels:

| Level | What's Logged |
|-------|---------------|
| `INFO` | Tool invocation, completion, key results |
| `ERROR` | Timeouts, connection failures |

Example logs:
```
INFO - Checking database access
INFO - Database access check completed: accessible=True
ERROR - Database access check timed out after 30s
```

---

## Client Usage

### Commands

```bash
# Check database access
python3 tests/postgres_diagnostic_client.py check-access

# Check write locks
python3 tests/postgres_diagnostic_client.py check-locks

# Check connections
python3 tests/postgres_diagnostic_client.py check-connections

# Run all checks
python3 tests/postgres_diagnostic_client.py all
```

### Client Options

| Option | Description |
|--------|-------------|
| `--server-url` | MCP server URL (default: `http://localhost:8080/mcp`) |
| `--database-url` | Custom PostgreSQL connection URL |

---

## Configuration

PostgreSQL connection settings in `src/config/settings.py`:

| Setting | Default | Environment Variable |
|---------|---------|---------------------|
| `postgres_host` | `localhost` | `POSTGRES_HOST` |
| `postgres_port` | `5432` | `POSTGRES_PORT` |
| `postgres_database` | `hotel_booking_db` | `POSTGRES_DATABASE` |
| `postgres_user` | `postgres` | `POSTGRES_USER` |
| `postgres_password` | `password` | `POSTGRES_PASSWORD` |
| `postgres_timeout` | `10` | `POSTGRES_TIMEOUT` |

Override via environment variables:
```bash
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_PASSWORD=mypassword
python3 -m src.main
```

---

## Files

Paths in the tables below are relative to `diagnostics/mcp-server/`.

### PostgreSQL Tools
| File | Description |
|------|-------------|
| `src/tools/db_check_access.py` | Database accessibility check |
| `src/tools/db_check_locks.py` | Write locks check |
| `src/tools/db_check_connections.py` | Max connections check |
| `src/models/postgres_diagnostics.py` | PostgreSQL Pydantic response models |

### Kafka Tools
| File | Description |
|------|-------------|
| `src/tools/get_consumer_lag.py` | Consumer lag check |
| `src/models/consumer_lag.py` | Kafka Pydantic response models |

### Booking Demo
Booking-specific tools, models, client, and runbook are under
[`demos/booking-demo/`](../../demos/booking-demo/README.md).

### Configuration & Clients
| File | Description |
|------|-------------|
| `src/config/settings.py` | PostgreSQL & Kafka configuration |
| `src/main.py` | MCP server entry point |
| `tests/postgres_diagnostic_client.py` | Core PostgreSQL CLI client |
| `tests/multi_server_client.py` | Multi-server MCP client |

