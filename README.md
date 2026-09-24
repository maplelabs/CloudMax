# AI-SRE-Ops

AI-powered Site Reliability Engineering Alert Dashboard with automated, configurable LLM-backed triage.

> **Quick start:** This README covers starting the full application.

## Prerequisites

For the Docker-based full stack:

- Docker Engine with Docker Compose v2 (`docker compose`)
- GNU Make
- Internet access to build images and download dependencies; the ports published by the selected Compose workflow must be available

You do not need Node.js or Python to run the full stack in containers. For local development, use Node.js 18+ for the frontend and Python 3.12+ for the backend. Model-backed features also require credentials for the provider you configure.

## Quick start: full application

Run these commands from the repository root. On first use, create local configuration files from the examples:

```bash
cp core/backend/.env.example core/backend/.env
cp agents/code-triage/.env.example agents/code-triage/.env
```

Edit the local files for the integrations you intend to use. Keep populated `.env` files private and do not commit them. Both files are required by the full-stack Compose setup; the Makefile checks for them before starting.

Start the application:

```bash
make full-stack up
```

The first start builds the application images and starts the services. Then open:

- Frontend: <https://localhost:3101> (the local HTTPS certificate may trigger a browser warning)
- Backend API: <http://localhost:8080>
- Langfuse: <http://localhost:3000>

Check status or stop the stack with separate commands, also from the repository root:

```bash
make full-stack status
make full-stack down
```

`down` preserves named data volumes. Database migrations run automatically when the stack starts; see [Database Migrations](#database-migrations) for manual commands.

## Local development workflows

The two development stacks run supporting services in Docker while you run one application component locally. Start and stop each stack from the repository root.

### Develop the frontend locally

```bash
# Terminal 1, from the repository root
make frontend-development-stack up

# Terminal 2
cd core/frontend
npm ci
npm run dev
```

Open the Vite frontend at <http://localhost:3000>. The backend API is at <http://localhost:8000>, and Langfuse is at <http://localhost:3001> in this workflow. Stop the Docker services with `make frontend-development-stack down` from the repository root.

### Develop the backend locally

First start the supporting services:

```bash
make backend-development-stack up
```

From the repository root, start a second terminal. Create and activate a virtual environment, install the backend requirements, and start the API:

```bash
cd core/backend
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r py_requirements.txt
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The backend API is at <http://localhost:8000>; the containerized frontend is at <https://localhost:8443> (with a local-certificate warning). Stop supporting services with `make backend-development-stack down` from the repository root.

Run `make help` for the available Make targets and commands.

### MCP mTLS testing

The default `make full-stack up` workflow runs locally with mTLS disabled. To test the mTLS-enabled configuration, use:

```bash
make full-stack-mtls up
```

This mode requires valid client certificates to be configured. It is a local integration-test option, not production deployment guidance. Stop it with `make full-stack-mtls down`.

For MCP-specific configuration and troubleshooting, see the [Diagnostic MCP Server documentation](#diagnostic-mcp-server).

## Database Migrations

The backend uses Alembic for database schema management. Migrations run automatically when starting the stack, but you can also run them manually:

```bash
# Generate migration from model changes
make migrate-autogenerate MESSAGE="Add user table"

# Apply all pending migrations
make migrate-upgrade

# Check current migration status
make migrate-current

# View migration history
make migrate-history

# Rollback one migration
make migrate-downgrade REVISION=-1

# Create empty migration for custom SQL
make migrate-revision MESSAGE="Add custom index"
```

**Notes:**

- Migrations run automatically in Docker containers before the backend starts
- Always review generated migrations before applying them
- Use descriptive messages for better tracking

## Optional Container Image Publishing

The Docker Compose workflows above do not require publishing images to a registry. For a separate registry build, the Makefile uses Docker Buildx to build and push the backend and frontend images. Authenticate to the target registry first, and supply an explicit version because no deployment overlay provides a default tag.

```bash
# Build and push for the current machine's platform
make docker-build-push VERSION=v1.54.1

# Build and push AMD64 + ARM64 images
make docker-build-multiplatform VERSION=v1.54.1
```

The image repositories are configured by `REGISTRY` and `IMAGE_NAMESPACE` in the Makefile. Override `REGISTRY` for your target registry as needed. These targets only publish images; they do not deploy or update the Docker Compose stack.

## Grafana Webhook Setup

To forward alerts from Grafana to the Alert Dashboard, configure a webhook in the Grafana UI.

#### 1. Create a Contact Point

- In Grafana, go to **Alerting → Contact points**.  
- Click **+ Create contact point**.  
- Enter a **Name** (e.g., `sre-alert-webhook`).  
- Under **Integration**, select **Webhook**.  
- Paste the **Webhook URL** (from the Alert Dashboard backend).  
- Click **Save contact point**.  

#### 2. Create a Notification Policy

- Go to **Alerting → Notification policies**.  
- Click **+ New child policy** (or edit the default one).  
- (Optional) Add **matching labels** if needed to filter alerts.  
- In the **Contact point** dropdown, select the webhook created earlier.  
- Click **Save policy**.  

Grafana alerts matching the policy will now be sent to the Alert Dashboard.

## Diagnostic MCP Server

For setup, configuration, troubleshooting, and system architecture of the diagnostic MCP server, see the [Diagnostic MCP Server guide](./diagnostics/mcp-server/README.md). Booking-specific diagnostics are covered in the [Booking Demo documentation](./demos/booking-demo/README.md).
