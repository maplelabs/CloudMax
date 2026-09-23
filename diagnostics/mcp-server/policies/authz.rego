package diagnostic_tools

import future.keywords.if
import future.keywords.in

# Default deny - if no rule allows, deny by default (fail-safe)
default allow = false

# ============================================================================
# Helper Functions
# ============================================================================

# Extract client_id from input
# Can come from:
# 1. Nginx auth_request (input.client_id contains CN from cert)
# 2. MCP middleware (input.client_id from X-Client-DN header)
client_id := cn if {
	input.client_id
	# Extract CN from DN format: "CN=mcp-client,OU=..."
	parts := split(input.client_id, ",")
	some part in parts
	startswith(part, "CN=")
	cn := trim_prefix(part, "CN=")
} else := input.client_id if {
	input.client_id
	not contains(input.client_id, "CN=")
}

# ============================================================================
# Public Endpoints (No Authentication Required)
# ============================================================================

# Allow health check endpoint
allow if {
	input.method == "GET"
	input.path == "/health"
}

# Allow health check endpoint (HTTP method check)
allow if {
	input.method == "GET"
	contains(input.path, "/health")
}

# Allow root endpoint
allow if {
	input.method == "GET"
	input.path == "/"
}

# ============================================================================
# MCP Protocol Authorization - Simple CN-based Authorization
# ============================================================================

# Allow ALL requests if client_id is "mcp-client" (mTLS enabled with valid cert)
allow if {
	client_id == "mcp-client"
}

# Allow ALL requests if ssl_verify is "NONE" (mTLS disabled - no cert verification)
# This is set by nginx when MCP_MTLS_ENABLED=false
allow if {
	input.ssl_verify == "NONE"
}
