# Documentation

- [Repository quick start](../README.md)
- [Security policy](../SECURITY.md)
- [Contribution guide](../CONTRIBUTING.md)
- [Diagnostic MCP PostgreSQL guide](integrations/postgres-diagnostics.md)
- [Diagnostic MCP server guide](../diagnostics/mcp-server/README.md)
- [Code-triage service guide](../agents/code-triage/README.md)
- [Booking diagnostics demo](../demos/booking-demo/README.md)

The backend's Kubernetes, Kafka, database, APM, and code-triage agents remain
in `core/backend/` because they are wired into the application's orchestration.
The separately deployable code-triage service lives in `agents/code-triage/`.
The current Confluence integration also remains part of the backend; it is not
an isolated plugin yet.
