# SRE Ops AI - Docker Compose and Image Publishing Makefile
# Manages local Docker Compose workflows and optional registry image publishing

# =============================================================================
# Configuration - Update these values for your environment
# =============================================================================
# Keep image repositories aligned with the configured registry.
REGISTRY ?= xoriantxlabs-eebqbgaud8badcdj.azurecr.io
IMAGE_NAMESPACE := ai-sre-ops
BACKEND_IMAGE := $(REGISTRY)/$(IMAGE_NAMESPACE)/backend
FRONTEND_IMAGE := $(REGISTRY)/$(IMAGE_NAMESPACE)/frontend

# Default configuration for the application
DEFAULT_API_URL := http://backend:8000

# Docker buildx platform (auto-detect or default to ARM64, can be overridden)
PLATFORM ?= linux/$(shell uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/; s/arm64/arm64/; /^amd64$$/!s/.*/arm64/')
# Multiplatform build support (AMD64 + ARM64)
MULTIPLATFORM := linux/amd64,linux/arm64

.PHONY: help full-stack full-stack-mtls frontend-development-stack backend-development-stack docker-build-push docker-build-multiplatform

# Default target
help:
	@echo "SRE Ops AI - Docker Stack Management"
	@echo ""
	@echo "Requirements for local stacks: Docker Engine, Docker Compose v2, and GNU Make"
	@echo "First-time setup from the repository root:"
	@echo "  cp core/backend/.env.example core/backend/.env"
	@echo "  cp agents/code-triage/.env.example agents/code-triage/.env (full stack)"
	@echo "  Keep populated .env files private; configure credentials only for integrations you use."
	@echo ""
	@echo "Stack Management:"
	@echo "  make full-stack up                    - Start the complete stack using docker-compose.yml [mTLS: disabled]"
	@echo "  make full-stack down                  - Stop complete stack"
	@echo "  make full-stack restart               - Restart complete stack"
	@echo "  make full-stack status                - Show complete stack status"
	@echo "  make full-stack-mtls up               - Start docker-compose.yml with mTLS enabled (requires certificates)"
	@echo "  make full-stack-mtls down             - Stop complete stack (mTLS mode)"
	@echo "  make full-stack-mtls restart          - Restart complete stack (mTLS mode)"
	@echo "                                          Access: Frontend https://localhost:3101 (use HTTPS directly)"
	@echo "                                                  Backend API http://localhost:8080"
	@echo "                                          Note: HTTPS uses self-signed certificates (browser warnings expected)"
	@echo ""
	@echo "  make frontend-development-stack up    - Start backend services; run 'cd core/frontend && npm ci && npm run dev' locally"
	@echo "  make frontend-development-stack down  - Stop frontend development stack"
	@echo "  make frontend-development-stack restart - Restart frontend development stack"
	@echo "  make frontend-development-stack status - Show frontend development stack status"
	@echo "                                          Access: Backend http://localhost:8000, Langfuse http://localhost:3001, Frontend dev http://localhost:3000"
	@echo ""
	@echo "  make backend-development-stack up     - Start dependencies; install backend requirements and run Uvicorn locally"
	@echo "  make backend-development-stack down   - Stop backend development stack"
	@echo "  make backend-development-stack restart - Restart backend development stack"
	@echo "  make backend-development-stack status - Show backend development stack status"
	@echo "                                          Access: Frontend https://localhost:8443 (use HTTPS directly)"
	@echo "                                                  Backend dev http://localhost:8000"
	@echo "                                          Note: HTTPS uses self-signed certificates (browser warnings expected)"
	@echo ""
	@echo "Optional Image Publishing:"
	@echo "  docker-build-push VERSION=<tag>          - Build and push backend/frontend images"
	@echo "  docker-build-multiplatform VERSION=<tag> - Build and push AMD64 + ARM64 images"
	@echo "  Supply VERSION explicitly; these targets publish to the configured registry."
	@echo "  Examples:"
	@echo "    make docker-build-push VERSION=v1.54.1"
	@echo "    make docker-build-multiplatform VERSION=v1.54.1"
	@echo ""
	@echo "Database Migrations:"
	@echo "  migrate-autogenerate MESSAGE=\"<message>\" - Generate new migration from model changes"
	@echo "  migrate-upgrade                           - Apply all pending migrations"
	@echo "  migrate-downgrade REVISION=<revision>     - Downgrade to specific revision"
	@echo "  migrate-current                           - Show current migration revision"
	@echo "  migrate-history                           - Show migration history"
	@echo "  migrate-revision MESSAGE=\"<message>\"      - Create empty migration file"
	@echo "  Examples:"
	@echo "    make migrate-autogenerate MESSAGE=\"Add user table\""
	@echo "    make migrate-upgrade"
	@echo "    make migrate-current"
	@echo ""
	@echo "Configuration:"
	@echo "  REGISTRY=$(REGISTRY)"
	@echo "  BACKEND_IMAGE=$(BACKEND_IMAGE)"
	@echo "  FRONTEND_IMAGE=$(FRONTEND_IMAGE)"
	@echo "  VERSION=$(VERSION) (required for image publishing)"
	@echo "  PLATFORM=$(PLATFORM) (auto-detected, fallback: arm64)"
	@echo "  DEFAULT_API_URL=$(DEFAULT_API_URL)"

# Stack Management with Sub-commands
full-stack:
ifeq ($(filter up,$(MAKECMDGOALS)),up)
	@if [ ! -f core/backend/.env ]; then \
		echo "Error: core/backend/.env file not found."; \
		echo "Create it with: cp core/backend/.env.example core/backend/.env"; \
		exit 1; \
	elif [ ! -f agents/code-triage/.env ]; then \
		echo "Error: agents/code-triage/.env file not found."; \
		echo "Create it with: cp agents/code-triage/.env.example agents/code-triage/.env"; \
		exit 1; \
	else \
		echo "Starting full stack (mTLS: DISABLED - no certificates required)..."; \
		MCP_MTLS_ENABLED=false docker compose up -d --build; \
	fi
	@echo ""
	@echo "✅ Full stack is running!"
	@echo "MCP mTLS Mode: DISABLED (development mode)"
	@echo ""
	@echo "Access URLs:"
	@echo "  Frontend:    https://localhost:3101 (HTTPS - use this)"
	@echo "               http://localhost:3100  (HTTP - not recommended, redirect may not work)"
	@echo "               ⚠️  Note: Browser will warn about self-signed certificate - this is expected"
	@echo "  Backend API: http://localhost:8080"
	@echo "  Langfuse:    http://localhost:3000"
	@echo ""
else ifeq ($(filter down,$(MAKECMDGOALS)),down)
	@echo "Stopping full stack..."
	docker compose down
else ifeq ($(filter restart,$(MAKECMDGOALS)),restart)
	@echo "Restarting full stack (mTLS: DISABLED)..."
	MCP_MTLS_ENABLED=false docker compose down && MCP_MTLS_ENABLED=false docker compose up -d --build
	@echo ""
	@echo "✅ Full stack restarted!"
	@echo "MCP mTLS Mode: DISABLED (development mode)"
	@echo ""
	@echo "Access URLs:"
	@echo "  Frontend:    https://localhost:3101 (HTTPS - use this)"
	@echo "               http://localhost:3100  (HTTP - not recommended, redirect may not work)"
	@echo "               ⚠️  Note: Browser will warn about self-signed certificate - this is expected"
	@echo "  Backend API: http://localhost:8080"
	@echo "  Langfuse:    http://localhost:3000"
	@echo ""
else ifeq ($(filter status,$(MAKECMDGOALS)),status)
	@echo "Full stack status:"
	docker compose ps
else
	@echo "Usage: make full-stack [up|down|restart|status]"
endif

# Full Stack with mTLS ENABLED (Production-like testing)
full-stack-mtls:
ifeq ($(filter up,$(MAKECMDGOALS)),up)
	@if [ ! -f core/backend/.env ]; then \
		echo "Error: core/backend/.env file not found."; \
		echo "Create it with: cp core/backend/.env.example core/backend/.env"; \
		exit 1; \
	elif [ ! -f agents/code-triage/.env ]; then \
		echo "Error: agents/code-triage/.env file not found."; \
		echo "Create it with: cp agents/code-triage/.env.example agents/code-triage/.env"; \
		exit 1; \
	else \
		echo "Starting full stack (mTLS: ENABLED - certificates REQUIRED)..."; \
		echo "⚠️  Make sure certificates are configured in the database for MCP connections!"; \
		MCP_MTLS_ENABLED=true docker compose up -d --build; \
	fi
	@echo ""
	@echo "✅ Full stack is running!"
	@echo "MCP mTLS Mode: ENABLED (local integration-test mode)"
	@echo "⚠️  Backend MUST have valid certificates to connect to MCP server"
	@echo ""
	@echo "Access URLs:"
	@echo "  Frontend:    https://localhost:3101 (HTTPS - use this)"
	@echo "               http://localhost:3100  (HTTP - not recommended, redirect may not work)"
	@echo "               ⚠️  Note: Browser will warn about self-signed certificate - this is expected"
	@echo "  Backend API: http://localhost:8080"
	@echo "  Langfuse:    http://localhost:3000"
	@echo ""
else ifeq ($(filter down,$(MAKECMDGOALS)),down)
	@echo "Stopping full stack..."
	docker compose down
else ifeq ($(filter restart,$(MAKECMDGOALS)),restart)
	@echo "Restarting full stack (mTLS: ENABLED)..."
	MCP_MTLS_ENABLED=true docker compose down && MCP_MTLS_ENABLED=true docker compose up -d --build
	@echo ""
	@echo "✅ Full stack restarted!"
	@echo "MCP mTLS Mode: ENABLED (local integration-test mode)"
	@echo "⚠️  Backend MUST have valid certificates to connect to MCP server"
	@echo ""
	@echo "Access URLs:"
	@echo "  Frontend:    https://localhost:3101 (HTTPS - use this)"
	@echo "               http://localhost:3100  (HTTP - not recommended, redirect may not work)"
	@echo "               ⚠️  Note: Browser will warn about self-signed certificate - this is expected"
	@echo "  Backend API: http://localhost:8080"
	@echo "  Langfuse:    http://localhost:3000"
	@echo ""
else ifeq ($(filter status,$(MAKECMDGOALS)),status)
	@echo "Full stack status (mTLS mode):"
	@docker compose ps
	@echo ""
	@echo "Check MCP nginx mTLS status:"
	@docker logs mcp-nginx 2>&1 | grep -i "mtls" | tail -2 || echo "Could not retrieve mTLS status"
else
	@echo "Usage: make full-stack-mtls [up|down|restart|status]"
endif

frontend-development-stack:
ifeq ($(filter up,$(MAKECMDGOALS)),up)
	@if [ ! -f core/backend/.env ]; then \
		echo "Error: core/backend/.env file not found."; \
		echo "Create it with: cp core/backend/.env.example core/backend/.env"; \
		exit 1; \
	else \
		echo "Starting frontend development stack..."; \
		docker compose -f docker-compose.frontend-dev.yml up --build -d; \
	fi
	@echo ""
	@echo "Frontend development stack is running!"
	@echo "Access URLs:"
	@echo "  Backend API: http://localhost:8000"
	@echo "  Langfuse:    http://localhost:3001"
	@echo ""
	@echo "To start frontend development:"
	@echo "  cd core/frontend && npm install && npm run dev"
	@echo "  Frontend dev server will be available at: http://localhost:3000"
	@echo ""
else ifeq ($(filter down,$(MAKECMDGOALS)),down)
	@echo "Stopping frontend development stack..."
	docker compose -f docker-compose.frontend-dev.yml down
else ifeq ($(filter restart,$(MAKECMDGOALS)),restart)
	@echo "Restarting frontend development stack..."
	docker compose -f docker-compose.frontend-dev.yml restart
	@echo ""
	@echo "Frontend development stack restarted!"
	@echo "Access URLs:"
	@echo "  Backend API: http://localhost:8000"
	@echo "  Langfuse:    http://localhost:3001"
	@echo ""
	@echo "To start frontend development:"
	@echo "  cd core/frontend && npm install && npm run dev"
	@echo "  Frontend dev server will be available at: http://localhost:3000"
	@echo ""
else ifeq ($(filter status,$(MAKECMDGOALS)),status)
	@echo "Frontend development stack status:"
	docker compose -f docker-compose.frontend-dev.yml ps
else
	@echo "Usage: make frontend-development-stack [up|down|restart|status]"
endif

backend-development-stack:
ifeq ($(filter up,$(MAKECMDGOALS)),up)
	@if [ ! -f core/backend/.env ]; then \
		echo "Error: core/backend/.env file not found."; \
		echo "Create it with: cp core/backend/.env.example core/backend/.env"; \
		exit 1; \
	else \
		echo "Starting backend development stack..."; \
		docker compose -f docker-compose.backend-dev.yml up --build -d; \
	fi
	@echo ""
	@echo "✅ Backend development stack is running!"
	@echo ""
	@echo "Access URLs:"
	@echo "  Frontend:    https://localhost:8443 (HTTPS - use this)"
	@echo "               http://localhost:8080  (HTTP - not recommended, redirect may not work)"
	@echo "               ⚠️  Note: Browser will warn about self-signed certificate - this is expected"
	@echo "  Langfuse:    http://localhost:3000"
	@echo "  Postgres:    localhost:5432"
	@echo ""
	@echo "Checking if backend is running..."
	@if ! curl -f -s http://localhost:8000/health > /dev/null 2>&1; then \
		echo "WARNING: Backend is not running on http://localhost:8000. Frontend container WOULD HAVE failed."; \
		echo "Please start your backend: cd core/backend && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"; \
	fi
else ifeq ($(filter down,$(MAKECMDGOALS)),down)
	@echo "Stopping backend development stack..."
	docker compose -f docker-compose.backend-dev.yml down
else ifeq ($(filter restart,$(MAKECMDGOALS)),restart)
	@echo "Checking if backend is running..."
	@if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then \
		echo "Backend is running, restarting backend development stack..."; \
		docker compose -f docker-compose.backend-dev.yml restart; \
		echo ""; \
		echo "✅ Backend development stack restarted!"; \
		echo ""; \
		echo "Access URLs:"; \
		echo "  Frontend:    https://localhost:8443 (HTTPS - use this)"; \
		echo "               http://localhost:8080  (HTTP - not recommended, redirect may not work)"; \
		echo "               ⚠️  Note: Browser will warn about self-signed certificate - this is expected"; \
		echo "  Langfuse:    http://localhost:3000"; \
		echo "  Postgres:    localhost:5432"; \
		echo ""; \
	else \
		echo "ERROR: Backend is not running on http://localhost:8000"; \
		echo ""; \
		echo "Please ensure your backend is running before restarting the stack:"; \
		echo "  cd core/backend && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"; \
		echo ""; \
		exit 1; \
	fi
else ifeq ($(filter status,$(MAKECMDGOALS)),status)
	@echo "Backend development stack status:"
	docker compose -f docker-compose.backend-dev.yml ps
else
	@echo "Usage: make backend-development-stack [up|down|restart|status]"
endif

# Make sub-commands work
up down restart status:
	@:

# Build images for optional registry publishing.
_docker-build-push-unified:
	@$(MAKE) _setup-build-environment MULTIPLATFORM_BUILD=$(MULTIPLATFORM_BUILD)
	@$(MAKE) _build-and-push-images MULTIPLATFORM_BUILD=$(MULTIPLATFORM_BUILD) VERSION=$(VERSION)

# Setup build environment variables
_setup-build-environment:
	@if [ "$(MULTIPLATFORM_BUILD)" = "true" ]; then \
		echo "Building multiplatform images (AMD64+ARM64)..."; \
		if ! docker buildx inspect multiplatform-builder >/dev/null 2>&1; then \
			echo "Creating multiplatform builder..."; \
			docker buildx create --name multiplatform-builder --driver docker-container --bootstrap; \
		fi; \
	else \
		echo "Building single-platform images..."; \
	fi

# Build and push backend/frontend images to the configured registry.
_build-and-push-images:
	@set -e; \
	BUILD_PLATFORM=$$(if [ "$(MULTIPLATFORM_BUILD)" = "true" ]; then echo "$(MULTIPLATFORM)"; else echo "$(PLATFORM)"; fi); \
	BUILDER_ARG=$$(if [ "$(MULTIPLATFORM_BUILD)" = "true" ]; then echo "--builder multiplatform-builder"; fi); \
	echo "Building and pushing backend image ($(VERSION))..."; \
	docker buildx build $$BUILDER_ARG --platform $$BUILD_PLATFORM --push \
		-t $(BACKEND_IMAGE):$(VERSION) ./core/backend; \
	echo "Building and pushing frontend image ($(VERSION))..."; \
	docker buildx build $$BUILDER_ARG --platform $$BUILD_PLATFORM --push \
		--build-arg BACKEND_URL=$(DEFAULT_API_URL) \
		-t $(FRONTEND_IMAGE):$(VERSION) ./core/frontend; \
	echo "Images built and pushed successfully!"; \
	echo "  Platform: $$BUILD_PLATFORM"; \
	echo "  Backend:  $(BACKEND_IMAGE):$(VERSION)"; \
	echo "  Frontend: $(FRONTEND_IMAGE):$(VERSION)"


# Docker Build and Push (single platform)
docker-build-push:
ifndef VERSION
	@echo "Error: VERSION is required. Set VERSION=<tag> when invoking this target."
	@exit 1
else
	@$(MAKE) _docker-build-push-unified MULTIPLATFORM_BUILD=false VERSION=$(VERSION)
endif

# Docker Build and Push (multiplatform)
docker-build-multiplatform:
ifndef VERSION
	@echo "Error: VERSION is required. Set VERSION=<tag> when invoking this target."
	@exit 1
else
	@$(MAKE) _docker-build-push-unified MULTIPLATFORM_BUILD=true VERSION=$(VERSION)
endif





# =============================================================================
# Database Migration Commands
# =============================================================================

# Generate new migration from model changes
migrate-autogenerate:
ifndef MESSAGE
	@echo "Error: Migration message not specified. Use: make migrate-autogenerate MESSAGE=\"<message>\""
	@echo "Example: make migrate-autogenerate MESSAGE=\"Add user table\""
	@exit 1
else
	@echo "Generating new migration: $(MESSAGE)"
	@cd core/backend && alembic -c src/alembic.ini revision --autogenerate -m "$(MESSAGE)"
endif

# Apply all pending migrations
migrate-upgrade:
	@echo "Applying all pending migrations..."
	@cd core/backend && alembic -c src/alembic.ini upgrade head

# Downgrade to specific revision
migrate-downgrade:
ifndef REVISION
	@echo "Error: Revision not specified. Use: make migrate-downgrade REVISION=<revision>"
	@echo "Example: make migrate-downgrade REVISION=base"
	@echo "         make migrate-downgrade REVISION=-1"
	@exit 1
else
	@echo "Downgrading to revision: $(REVISION)"
	@cd core/backend && alembic -c src/alembic.ini downgrade $(REVISION)
endif

# Show current migration revision
migrate-current:
	@echo "Current migration revision:"
	@cd core/backend && alembic -c src/alembic.ini current

# Show migration history
migrate-history:
	@echo "Migration history:"
	@cd core/backend && alembic -c src/alembic.ini history --verbose

# Create empty migration file
migrate-revision:
ifndef MESSAGE
	@echo "Error: Migration message not specified. Use: make migrate-revision MESSAGE=\"<message>\""
	@echo "Example: make migrate-revision MESSAGE=\"Add custom index\""
	@exit 1
else
	@echo "Creating empty migration: $(MESSAGE)"
	@cd core/backend && alembic -c src/alembic.ini revision -m "$(MESSAGE)"
endif

