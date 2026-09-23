#!/bin/sh
set -e

if [ "${MTLS_ENABLED}" = "true" ]; then
    echo "mTLS ENABLED: Using HTTPS with client certificate validation"

    # Check if required certificates exist in mounted directory
    if [ ! -f /etc/nginx/certs/server-cert.pem ] || [ ! -f /etc/nginx/certs/server-key.pem ]; then
        echo "ERROR: mTLS is enabled but certificates are missing!"
        echo "Please mount certificates to /etc/nginx/certs/"
        exit 1
    fi

    # Generate HTTPS configuration with mTLS
    cat > /etc/nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;

    resolver 127.0.0.11 valid=10s ipv6=off;
    resolver_timeout 5s;

    server {
        listen 8443 ssl;
        server_name localhost mcp.sre-ops.local;

        access_log /var/log/nginx/mcp_access.log main;
        error_log /var/log/nginx/mcp_error.log warn;

        ssl_certificate /etc/nginx/certs/server-cert.pem;
        ssl_certificate_key /etc/nginx/certs/server-key.pem;
        ssl_client_certificate /etc/nginx/certs/ca-cert.pem;
        ssl_verify_client optional;
        ssl_verify_depth 2;

        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        set $client_dn $ssl_client_s_dn;

        location = /mcp {
            set $mtls_fail 0;

            if ($ssl_client_verify != SUCCESS) {
                set $mtls_fail 1;
            }

            if ($mtls_fail = 1) {
                return 403 '{"error":"Client certificate required","ssl_verify":"$ssl_client_verify"}';
            }

            auth_request /opa-authz;
            auth_request_set $auth_status $upstream_status;

            set $mcp_upstream mcp-server:8000;
            proxy_pass http://$mcp_upstream/mcp;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-SSL-Client-S-DN $client_dn;
            proxy_set_header X-SSL-Client-Verify $ssl_client_verify;

            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        location = / {
            default_type application/json;
            return 200 '{"service":"MCP Diagnostic Server","endpoint":"/mcp","mtls":"enabled"}';
        }

        location = /opa-authz {
            internal;
            set $opa_upstream opa:8181;
            proxy_pass http://$opa_upstream/v1/data/diagnostic_tools/allow;
            proxy_method POST;
            proxy_set_header Content-Type application/json;
            proxy_set_body '{"input":{"method":"$request_method","path":"$request_uri","client_id":"$client_dn","ssl_verify":"$ssl_client_verify"}}';
        }

        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
    }
}
EOF
else
    echo "mTLS DISABLED: Using plain HTTP (no SSL/TLS)"

    # Generate HTTP-only configuration
    cat > /etc/nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;

    resolver 127.0.0.11 valid=10s ipv6=off;
    resolver_timeout 5s;

    server {
        listen 8443;
        server_name localhost mcp.sre-ops.local;

        access_log /var/log/nginx/mcp_access.log main;
        error_log /var/log/nginx/mcp_error.log warn;

        location = /mcp {
            auth_request /opa-authz;
            auth_request_set $auth_status $upstream_status;

            set $mcp_upstream mcp-server:8000;
            proxy_pass http://$mcp_upstream/mcp;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        location = / {
            default_type application/json;
            return 200 '{"service":"MCP Diagnostic Server","endpoint":"/mcp","mtls":"disabled"}';
        }

        location = /opa-authz {
            internal;
            set $opa_upstream opa:8181;
            proxy_pass http://$opa_upstream/v1/data/diagnostic_tools/allow;
            proxy_method POST;
            proxy_set_header Content-Type application/json;
            proxy_set_body '{"input":{"method":"$request_method","path":"$request_uri"}}';
        }

        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
    }
}
EOF
fi

echo "nginx configuration generated successfully"

exec "$@"

