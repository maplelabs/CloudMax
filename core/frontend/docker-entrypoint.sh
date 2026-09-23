#!/bin/sh
set -e

echo "Starting frontend container..."
echo "Backend URL: ${BACKEND_URL}"

# Validate files exist
if [ ! -f /etc/nginx/nginx.conf.template ]; then
  echo "ERROR: nginx.conf.template not found"
  exit 1
fi

if [ ! -f /etc/nginx/certs/cert.pem ] || [ ! -f /etc/nginx/certs/key.pem ]; then
  echo "ERROR: TLS certificates not found in /etc/nginx/certs/"
  exit 1
fi

echo "TLS certificates validated"

# Log certificate expiry if available
if command -v openssl >/dev/null 2>&1; then
  CERT_EXPIRY=$(openssl x509 -enddate -noout -in /etc/nginx/certs/cert.pem)
  echo "Certificate expiry: ${CERT_EXPIRY}"
fi

# Substitute environment variables
envsubst "\$BACKEND_URL" < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

# Validate and start nginx
nginx -t
echo "Starting nginx..."
exec nginx -g "daemon off;"
