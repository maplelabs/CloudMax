# AI-SRE-Ops - Diagnostic MCP Server

**AI-Powered Site Reliability Engineering Platform with Automated Triage**

AI-powered diagnostic server for Kafka and PostgreSQL monitoring using the Model Context Protocol (MCP). Enables AI agents like AWS Bedrock Claude to autonomously diagnose and troubleshoot infrastructure through natural language.

---

## 📋 What is This System?

AI-SRE-Ops automatically diagnoses infrastructure issues using AI agents.

**What it does:**
1. Receives alerts from Grafana (API errors, high latency, etc.)
2. AI analyzes the alert using AWS Bedrock Claude
3. Runs diagnostics automatically (checks Kafka, databases, etc.)
4. Provides Root Cause Analysis with detailed findings
5. Shows results in a dashboard for engineers to review

**Key benefit:** Instead of engineers manually checking logs, Kafka lag, database connections, etc., the AI does it automatically in seconds.

---

## 🏗️ System Architecture

### Components Overview

```
Grafana Alert → Backend API → Triager (AI Agent)
                                    ↓
                          AWS Bedrock Claude
                                    ↓
                          MCP Diagnostic Server
                                    ↓
                    Kafka + PostgreSQL Diagnostics
```

**1. Frontend (React)** - Dashboard to view alerts and triage results

**2. Backend (FastAPI)** - REST API for alert ingestion, stores data in PostgreSQL

**3. Triager (RQ Worker)** - AI agent using AWS Bedrock Claude, calls diagnostic tools via MCP

**4. MCP Diagnostic Server** - Provides generic Kafka lag and PostgreSQL health diagnostics; booking DLQ checks are isolated in the optional demo.

**5. Supporting Services** - PostgreSQL, Redis, Kafka, Langfuse (observability)

---

## Features

- **MCP Server** - Exposes diagnostic tools via HTTP/HTTPS
- **AI Integration** - AWS Bedrock Claude Sonnet 4 tested and working
- **Kubernetes** - Can be deployed with an organization-maintained chart; no chart is bundled here
- **Optional mTLS** - Client certificate authentication with OPA authorization
- **Multi-Agent System** - Specialized agents for Kafka, Database, Kubernetes, APM
- **Core diagnostics** - Health, Kafka consumer lag, and PostgreSQL access/locks/connections
- **Booking demo** - Optional booking-specific MCP tools isolated under `../../demos/booking-demo/`
- **FastMCP 2.13.2** - MCP protocol implementation

---

## 🚀 Quick Start - Full Platform

### Prerequisites
- Docker & Docker Compose
- AWS Account with Bedrock access
- AWS credentials with Claude Sonnet 4 enabled

### Step 1: Setup Environment

```bash
git clone <repository-url>
cd ai-sre-ops
cp core/backend/.env.example core/backend/.env
```

Edit the local environment file and supply your own AWS credentials and configuration. Do not commit populated environment files or credential values:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (e.g., us-west-2)
- `BEDROCK_MODEL_ID` (e.g., us.anthropic.claude-sonnet-4-20250514-v1:0)

### Step 2: Start the System

```bash
make full-stack up
```

Wait 2-3 minutes. This starts:
- Frontend: http://localhost:3001
- Backend API: http://localhost:8080
- Triager, MCP Server, PostgreSQL, Redis, Kafka, Langfuse

### Step 3: Configure MCP Connection

Open http://localhost:3001

1. Go to: **Setup → Integrations → Diagnostic MCP Servers**
2. Add MCP Server:
   - Name: "Diagnostic Server"
   - Endpoint URL: `https://mcp-nginx:8443/mcp`
   - mTLS: Disabled
3. Click "Test Connection" → Should succeed
4. Click "Save"

**Done!** System is ready.

---

## 🔧 How to Use

### Trigger a Triage

**From Grafana (Production):**
- Configure Grafana webhook: `http://backend:8080/v1/alerts/webhook`
- Alert fires → Automatic triage

**From UI (Testing):**
- Go to Alerts page
- Click "Triage" button on an alert
- Watch AI analyze the issue

### View Results

Results show in UI:
- AI analysis and reasoning
- Diagnostic tool results (Kafka lag, DB status, etc.)
- Root cause analysis
- Recommended actions

---

## 📊 Available Diagnostics

### Kafka
- Consumer Lag: Check if consumers are falling behind
- Dead Letter Queue: Analyze failed messages
- Topic Info: Get topic configuration

### Database
- Connection Check: Verify connectivity
- Write Locks: Detect blocking queries
- Connection Pool: Monitor active connections
- Data Presence: Check if records exist

### Health
- Server status and uptime

**How it works:** AI decides which tools to call based on alert context.

---

## 🚀 Quick Start - MCP Server Only

### Kubernetes Deployment

This repository does not include a Kubernetes chart or deployment helper. Use
an organization-maintained chart and its values/secrets, or use the supported
Docker Compose workflow below.

### Local Development (Docker Compose)

```bash
cd diagnostics/mcp-server

# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Start dependencies without the MCP container (run the server locally below)
docker compose up -d zookeeper kafka opa

# 3. Run MCP server
python3 src/main.py --host 0.0.0.0 --port 8000

# 4. Test with scripts
python3 tests/kafka_producer.py --messages 100
python3 tests/create_consumer_lag.py --consume 10
python3 tests/multi_server_client.py test-consumer-group test-topic
```

The repository-level Compose entry points (`docker-compose.yml`,
`docker-compose.backend-dev.yml`, and `docker-compose.frontend-dev.yml`) remain
at the repository root. The root stack's MCP Nginx proxy image is built from
`docker/nginx/` within this integration.

---

## Project Structure

```
mcp-server/
├── src/                           # Source code
│   ├── main.py                    # MCP server entry point
│   ├── config/                    # Configuration
│   ├── models/                    # Pydantic models
│   ├── tools/                     # Diagnostic tools
│   └── middleware/                # OPA authorization middleware
├── tests/                         # Test scripts
│   ├── test_with_bedrock_https.py # AWS Bedrock integration test
│   ├── kafka_producer.py          # Generate test data
│   ├── create_consumer_lag.py     # Create consumer lag
│   └── multi_server_client.py     # MCP client
├── nginx/                         # Nginx configs
│   ├── http.conf                  # HTTP mode
│   └── https-mtls.conf            # HTTPS with mTLS
├── docker/nginx/                  # Root Compose MCP proxy image assets
│   ├── Dockerfile.mcp
│   └── docker-entrypoint-mcp.sh
├── policies/                      # OPA policies
│   └── authz.rego                 # Authorization rules
├── scripts/                       # Helper scripts
│   └── generate-certs.sh          # Generate mTLS certs in certs/
├── docker-compose.yml             # Local Kafka setup
├── Dockerfile                     # Docker image
└── requirements.txt               # Python dependencies
```

---

## Local Deployment Modes

For the in-repository Docker Compose stack, run these commands from
`diagnostics/mcp-server/`:

### HTTP development

```bash
docker compose --profile http up -d
```

### HTTPS with mTLS (local testing)

Generate certificates first, then start the HTTPS profile:

```bash
bash scripts/generate-certs.sh
docker compose --profile https up -d
```

Generated certificates are written to the ignored `certs/` directory and
mounted into Nginx by both Compose stacks. For Kubernetes deployments, provide
an external chart and follow its deployment and secret-management instructions.

---

## Kubernetes / Helm Deployment

This repository does not bundle Kubernetes chart sources or a deployment
helper. For Kubernetes, use your organization's chart and its documented
values and secret-management process. The local HTTP and mTLS Compose workflows
above are the deployment paths included in this repository.

---

## Core Available Tools

The core MCP server exposes five domain-neutral tools:

- `health_check` — check server health.
- `get_consumer_lag_tool` — inspect lag for a Kafka consumer group.
- `db_check_access_tool` — check PostgreSQL reachability.
- `db_check_write_locks_tool` — check for pending write locks.
- `db_check_max_connections_tool` — inspect PostgreSQL connection usage.

Booking-specific presence, time-range, processing, and DLQ tools are not loaded
by the core server. See the [Booking Diagnostics Demo](../../demos/booking-demo/README.md)
for the separate demo server and usage instructions.

---

## Configuration

### Environment Variables

```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# mTLS Mode
MTLS_ENABLED=false  # true for mTLS mode

# OPA (when mTLS enabled)
OPA_URL=http://localhost:8181
```

### Services

| Service | Local Port | Kubernetes Port |
|---------|------------|-----------------|
| Kafka | 9092 | - |
| Zookeeper | 2181 | - |
| MCP Server (HTTP) | 8000 | 30445 |
| MCP Server (HTTPS) | - | 30444 |
| OPA | 8181 | - |

---

## Test Scripts

Core test and client scripts are in the `tests/` folder. The booking-specific demo client is documented under [`demos/booking-demo/`](../../demos/booking-demo/README.md).

### Generate Test Data
```bash
python3 tests/kafka_producer.py --messages 100
```

### Create Consumer Lag
```bash
python3 tests/create_consumer_lag.py --consume 10
```

### Test MCP Client
```bash
python3 tests/multi_server_client.py test-consumer-group test-topic
```

### Full Integration Test
```bash
python3 tests/test_with_bedrock_https.py
```

---

## 🔐 Production Deployment (with mTLS)

For production, enable mTLS for secure communication.

### Step 1: Generate Certificates

```bash
cd diagnostics/mcp-server/scripts
bash generate-certs.sh
cd ../../..
```

The script generates certificates under `diagnostics/mcp-server/certs/`, which the root and local Compose stacks mount into Nginx. Keep the generated private keys out of version control.

### Step 2: Start with mTLS

```bash
make full-stack-mtls up
```

### Step 3: Configure Certificates in UI

In UI: **Setup → Integrations → Diagnostic MCP Servers**
1. Enable "mTLS" toggle
2. Upload the generated CA certificate, client certificate, and client key:
   - CA Certificate
   - Client Certificate
   - Client Key
3. Test Connection
4. Save

### Verify

```bash
docker compose logs mcp-nginx | grep -i mtls
```

Should show: "mTLS ENABLED: Client certificates REQUIRED"

---

## Kubernetes Deployment

No application or MCP Helm chart is bundled in this repository, and the root
Makefile does not provide a `helm-install` target. For cluster deployments,
use organization-maintained charts and their instructions. The supported
in-repository workflows use the root Docker Compose files and Make targets.

---

## 🔍 Troubleshooting

Full-stack commands in this section assume the repository-root Compose file;
run them from the repository root. For the standalone MCP stack, run commands
from `diagnostics/mcp-server/` and use only its declared services.

### Services Not Starting

```bash
# Check status
docker compose ps

# View logs
docker compose logs backend
docker compose logs triager
docker compose logs mcp-server

# Restart specific service
docker compose restart backend
```

### MCP Connection Test Fails

**Check 1: MCP server is running**
```bash
docker compose logs mcp-server | tail -20
```

**Check 2: Nginx is healthy**
```bash
docker compose logs mcp-nginx | tail -20
```

**Check 3: Endpoint URL is correct**
- Development: `https://mcp-nginx:8443/mcp`
- Kubernetes: use the endpoint exposed by your organization's chart.

### Triage Fails with AWS Bedrock Error

**Error: "tools.17.custom.name: String should match pattern"**

This was fixed! Tool names are now sanitized to replace spaces and dots with underscores.

**Verify fix:**
```bash
docker compose logs triager | grep -i "sanitiz"
```

Should show: "Sanitizing tool name: diagnostic __get_consumer_lag_tool → diagnostic___get_consumer_lag_tool"

**If still failing:**
```bash
# Rebuild services (the Make target builds images when starting)
make full-stack down
make full-stack up
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check database logs
docker compose logs postgres | tail -20

# Test connection
docker compose exec postgres psql -U otelu -d sreops -c "SELECT 1;"
```

### Pod not starting (Kubernetes)
```bash
kubectl describe pod -l component=mcp-server
kubectl logs -l component=mcp-server
```

### Rebuild and redeploy (Kubernetes)
Use the build and redeploy steps provided with your organization's chart; this
repository does not include the referenced Helm chart or build helper.

### Kafka connection error
```bash
docker compose restart kafka
docker compose logs kafka
```

### Delete deployment (Kubernetes)
```bash
helm uninstall mcp-opa-server
```

---

## 🛠️ Common Operations

### View Triager Logs

```bash
# Real-time logs
docker compose logs -f triager

# Last 100 lines
docker compose logs --tail=100 triager

# Search for errors
docker compose logs triager | grep -i error
```

### Restart Services

```bash
# Restart all
make full-stack restart

# Restart specific service
docker compose restart backend
docker compose restart triager
docker compose restart frontend
```

### Clean Up and Rebuild

```bash
# Stop everything
make full-stack down

# Remove volumes (WARNING: deletes data)
docker compose down -v

# Rebuild and start (the Make target builds images when starting)
make full-stack up
```

### Database Operations

```bash
# Run migrations
make migrate-upgrade

# Check migration status
make migrate-current

# Access database
docker compose exec postgres psql -U otelu -d sreops
```

---

## 📚 Key Concepts

### MCP (Model Context Protocol)

A standard protocol for AI agents to call tools. Think of it as an API that AI can understand and use.

**Why MCP?**
- Standardized way for AI to discover and call tools
- Language-agnostic
- Supports streaming responses
- Works with any LLM (AWS Bedrock, OpenAI, etc.)

### mTLS (Mutual TLS)

Two-way authentication where both client and server verify each other's certificates.

**When to use:**
- Development: mTLS disabled (easier, faster)
- Production: mTLS enabled (secure, compliant)

**How it works:**
1. Client sends certificate to server
2. Server verifies certificate
3. Server sends its certificate to client
4. Client verifies server certificate
5. Encrypted communication established

### Multi-Agent System

Instead of one AI doing everything, we have specialized agents:
- **Kafka Diagnostics Agent**: Handles Kafka-related issues
- **Database Diagnostics Agent**: Handles database issues
- **Kubernetes Observability Agent**: Handles Kubernetes issues
- **APM Observability Agent**: Handles application performance issues

**Benefits:**
- Each agent is expert in its domain
- Parallel execution
- Easier to maintain and extend

---

## Technology Stack

- **MCP Framework**: FastMCP 2.13.2
- **Language**: Python 3.12
- **Kafka Client**: confluent-kafka 2.3.0
- **AI Integration**: AWS Bedrock Claude Sonnet 4 (via langchain-mcp-adapters 0.1.14)
- **Security**: Nginx 1.25-alpine + OPA 0.70.0 (mTLS mode)
- **Orchestration**: Kubernetes + Helm 3.x
- **Frontend**: React + Vite
- **Backend**: FastAPI + PostgreSQL + Redis + RQ

---

## 📖 Additional Documentation

For more details, see:
- [Main project README](../../README.md)
- [Production mTLS instructions](#production-deployment-with-mtls)
- [System architecture overview](#system-architecture)
- [Multi-agent system overview](#multi-agent-system)

---

## ✅ Summary

**To get started:**
1. Create a local backend environment file from the example above and supply your own AWS credentials; do not commit the populated file.
2. `make full-stack up`
3. Configure MCP connection in UI
4. Trigger a triage!

**For production:**
1. Generate certificates: `bash diagnostics/mcp-server/scripts/generate-certs.sh`
2. `make full-stack-mtls up`
3. Upload certificates in UI

**Need help?**
- Check logs: `docker compose logs <service>`
- Restart: `make full-stack restart`
- Rebuild: `make full-stack down && make full-stack up`

---

## License

See LICENSE file for details.

**That's it! You're ready to use AI-SRE-Ops.** 🚀

