# Certificate domains (comma-separated)
ARG CERT_DOMAINS="cloudmax.xoriant.com,localhost"

# Certificate IPs (comma-separated)
ARG CERT_IP_ADDRESSES="127.0.0.1"

# Backend API URL
ARG BACKEND_URL=http://backend:8000

# Stage 1: Generate self-signed certificates
FROM golang:1.23-alpine AS cert-generator
ARG CERT_DOMAINS
ARG CERT_IP_ADDRESSES

RUN apk add --no-cache git
RUN go install github.com/jsha/minica@v1.1.0

WORKDIR /certs
RUN minica --domains "${CERT_DOMAINS}" --ip-addresses "${CERT_IP_ADDRESSES}"

# Normalize directory structure (minica creates dir named after first domain)
RUN PRIMARY_DOMAIN=$(echo "${CERT_DOMAINS}" | cut -d',' -f1) && \
    mv "${PRIMARY_DOMAIN}" primary-cert

# Stage 2: Build React application
FROM node:22 AS build
WORKDIR /app

COPY core/frontend/package*.json ./
RUN npm ci --silent

COPY core/frontend/ ./
COPY THIRD_PARTY_NOTICES.md ./public/THIRD_PARTY_NOTICES.md
RUN npm run build

# Stage 3: Nginx with HTTPS
FROM nginx:alpine
ARG BACKEND_URL

RUN apk add --no-cache gettext

COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=cert-generator /certs/minica.pem /etc/nginx/certs/ca.pem
COPY --from=cert-generator /certs/primary-cert/cert.pem /etc/nginx/certs/cert.pem
COPY --from=cert-generator /certs/primary-cert/key.pem /etc/nginx/certs/key.pem

COPY nginx.conf /etc/nginx/nginx.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80 443

CMD ["/docker-entrypoint.sh"]
