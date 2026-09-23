#!/bin/bash

# Certificate Generation Script for MCP Server mTLS
# This script generates a complete set of certificates for mTLS authentication

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="$SCRIPT_DIR/../certs"
mkdir -p "$CERTS_DIR"
cd "$CERTS_DIR"

echo "🔐 Generating mTLS Certificates for MCP Server"
echo "================================================"
echo ""

# Clean up old certificates
echo "🧹 Cleaning up old certificates..."
rm -f *.pem *.srl

# 1. Generate CA (Certificate Authority)
echo "📜 Step 1: Generating CA private key and certificate..."
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days 3650 -key ca-key.pem -out ca-cert.pem \
    -subj "/C=US/ST=California/L=San Francisco/O=SRE Ops/OU=Certificate Authority/CN=SRE Ops CA"

echo "   ✅ CA certificate generated (valid for 10 years)"

# 2. Generate Server Certificate
echo "📜 Step 2: Generating server private key and certificate..."
openssl genrsa -out server-key.pem 4096
openssl req -new -key server-key.pem -out server.csr \
    -subj "/C=US/ST=California/L=San Francisco/O=SRE Ops/OU=MCP Server/CN=mcp-nginx"

# Create server certificate extensions file
cat > server-ext.cnf <<EOF
subjectAltName = DNS:mcp-nginx,DNS:localhost,IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF

openssl x509 -req -days 3650 -in server.csr -CA ca-cert.pem -CAkey ca-key.pem \
    -CAcreateserial -out server-cert.pem -extfile server-ext.cnf

rm -f server.csr server-ext.cnf

echo "   ✅ Server certificate generated (valid for 10 years)"

# 3. Generate Client Certificate
echo "📜 Step 3: Generating client private key and certificate..."
openssl genrsa -out client-key.pem 4096
openssl req -new -key client-key.pem -out client.csr \
    -subj "/C=US/ST=California/L=San Francisco/O=SRE Ops/OU=Backend Client/CN=mcp-client"

# Create client certificate extensions file
cat > client-ext.cnf <<EOF
extendedKeyUsage = clientAuth
EOF

openssl x509 -req -days 3650 -in client.csr -CA ca-cert.pem -CAkey ca-key.pem \
    -CAcreateserial -out client-cert.pem -extfile client-ext.cnf

rm -f client.csr client-ext.cnf ca-cert.srl

echo "   ✅ Client certificate generated (valid for 10 years)"

# 4. Set proper permissions
echo "🔒 Setting proper file permissions..."
chmod 600 *.pem

echo ""
echo "✅ Certificate generation complete!"
echo ""
echo "📋 Generated files:"
echo "   - ca-cert.pem       (CA certificate - upload to UI)"
echo "   - ca-key.pem        (CA private key - keep secure)"
echo "   - server-cert.pem   (Server certificate - used by nginx)"
echo "   - server-key.pem    (Server private key - used by nginx)"
echo "   - client-cert.pem   (Client certificate - upload to UI)"
echo "   - client-key.pem    (Client private key - upload to UI)"
echo ""
echo "🎯 Next steps:"
echo "   1. Restart mcp-nginx and mcp-server containers to use new certificates"
echo "   2. In the UI, go to Setup → Integrations → Diagnostic MCP Servers"
echo "   3. Add a new server with endpoint: https://mcp-nginx:8443/mcp"
echo "   4. Enable mTLS and upload:"
echo "      - CA Certificate: ca-cert.pem"
echo "      - Client Certificate: client-cert.pem"
echo "      - Client Private Key: client-key.pem"
echo "   5. Test the connection"
echo ""
echo "📖 To view certificate contents:"
echo "   openssl x509 -in ca-cert.pem -text -noout"
echo "   openssl x509 -in server-cert.pem -text -noout"
echo "   openssl x509 -in client-cert.pem -text -noout"
echo ""

