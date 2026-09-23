# AI-SRE-Ops

AI-powered Site Reliability Engineering Alert Dashboard with automated triage using AWS Bedrock Claude.

> **🚀 Quick Start: See [diagnostic-mcp-server/README.md](./diagnostic-mcp-server/README.md)** - Complete guide to setup, run, and use the system

## Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for frontend development)
- Python 3.12+ (for backend development)
- AWS Account with Bedrock access

## Development Environment Setup (one-time)

```bash
# Backend
cp backend/.env.example backend/.env
```

Notes:

- Defaults are set for local development. Docker compose files override environment variables as needed.

## Development Workflows

Three docker-compose files support different development scenarios:

- **docker-compose.yml** - Complete stack with all services
- **docker-compose.frontend-dev.yml** - Backend containerized, frontend can be run locally with Vite
- **docker-compose.backend-dev.yml** - Frontend containerized, backend can be run locally for debugging

Use `up/down/status` for relevant operations:

```bash
# Full stack (mTLS disabled - default for development)
make full-stack up/down/status

# Full stack with mTLS enabled (for production-like testing)
make full-stack-mtls up/down/status

# Frontend development
make frontend-development-stack up/down/status

# Backend development
make backend-development-stack up/down/status

# Show all commands
make help
```

### MCP Server mTLS Modes

The MCP (Model Context Protocol) server supports two deployment modes:

- **Development Mode (mTLS disabled)** - Use `make full-stack up`
  - No client certificates required
  - Easier for local development and testing
  - Default mode

- **Production Mode (mTLS enabled)** - Use `make full-stack-mtls up`
  - Client certificates required for all connections
  - Enhanced security for production-like environments
  - Requires certificate configuration via UI

**📖 For complete setup and deployment instructions, see [diagnostic-mcp-server/README.md](./diagnostic-mcp-server/README.md)**

Additional resources:
- [diagnostic-mcp-server/ARCHITECTURE.md](./diagnostic-mcp-server/ARCHITECTURE.md) - Architecture details

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

## Docker Image Builds

```bash
# Build and push ARM images for integration
make docker-build-push ENV=integration

# Build and push ARM images for production (main branch only)
make docker-build-push ENV=production
```

## Kubernetes Deployment

### Setup Secrets

```bash
cp charts/ai-sre-app/.env.example charts/ai-sre-app/.env
# Set the OpenAI and Bedrock secrets in charts/ai-sre-app/.env
```

### Deploy

```bash
# Deploy to integration environment
make helm-deploy ENV=integration

# Deploy to production environment
make helm-deploy ENV=production
```

### Uninstall

```bash
# Uninstall from integration environment
make helm-uninstall ENV=integration

# Uninstall from production environment
make helm-uninstall ENV=production
```

## Configuration

### Version Management

Each component has its own version file:

- `frontend/version.txt` - Frontend version
- `backend/version.txt` - Backend version

Update these files to change image tags for builds.

### Registry Configuration

Update the `REGISTRY` variable in the Makefile to point to your container registry:

```makefile
REGISTRY := your-registry.com
```

### Grafana Webhook Setup

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

## Image Building Options
### Standard Build Commands

```bash
# Single-platform build (auto-detects your machine architecture, defaults to ARM64)
make docker-build-push ENV=integration

# Multiplatform build (AMD64 + ARM64)
make docker-build-multiplatform ENV=integration

# With optional suffix for custom tags
make docker-build-push ENV=dev SUFFIX=hotfix
make docker-build-multiplatform ENV=integration SUFFIX=rc1
```

### Platform Detection

The Makefile automatically detects your machine architecture:
- **Intel/AMD machines**: Builds for `linux/amd64`
- **ARM machines**: Builds for `linux/arm64`
- **Unknown architectures**: Defaults to `linux/arm64`

### Tag Generation

Images are tagged using the pattern: `{env-prefix}-v{version}[-suffix]`

Examples:
- `integration` → `int-v2.0.0`
- `production` → `prod-v2.0.0`
- `dev SUFFIX=hotfix` → `dev-v2.0.0-hotfix`
- `dev SUFFIX=arm64` → `dev-v2.0.0-arm64`
- `integration SUFFIX=amd64` → `int-v2.0.0-amd64`

### Architecture-Specific Building with SUFFIX

You can use the SUFFIX parameter to create architecture-specific tags, which is useful for distributed building or manual multiplatform manifest creation:

#### **Building for Specific Architectures:**

```bash
# Build ARM64 images (on ARM machine or forced)
make docker-build-push ENV=integration SUFFIX=arm64
# Results: int-v2.0.0-arm64

# Build AMD64 images (on Intel/AMD machine or forced)
make docker-build-push ENV=integration SUFFIX=amd64
# Results: int-v2.0.0-amd64
```

#### **Distributed Building: Manual Multiplatform Image Build**

1. **On AMD64 machine:**
   ```bash
   make docker-build-push ENV=integration SUFFIX=amd64
   ```

2. **On ARM64 machine:**
   ```bash
   make docker-build-push ENV=integration SUFFIX=arm64
   ```

3. **Create multiplatform manifest (on either machine):**
   ```bash
   TAG_BASE=int-v2.0.1

   # Backend manifest
   docker manifest create \
     thouqueerahmedml/cloud-sre-ops-ai-backend:$TAG_BASE \
     --amend thouqueerahmedml/cloud-sre-ops-ai-backend:$TAG_BASE-amd64 \
     --amend thouqueerahmedml/cloud-sre-ops-ai-backend:$TAG_BASE-arm64

   docker manifest push thouqueerahmedml/cloud-sre-ops-ai-backend:$TAG_BASE

   # Frontend manifest
   docker manifest create \
     thouqueerahmedml/cloud-sre-ops-ai-frontend:$TAG_BASE \
     --amend thouqueerahmedml/cloud-sre-ops-ai-frontend:$TAG_BASE-amd64 \
     --amend thouqueerahmedml/cloud-sre-ops-ai-frontend:$TAG_BASE-arm64

   docker manifest push thouqueerahmedml/cloud-sre-ops-ai-frontend:$TAG_BASE
   ```

