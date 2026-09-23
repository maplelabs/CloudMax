# Multi-stage build for MCP Server with Direct mTLS
FROM python:3.12-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY src/ ./src/
COPY policies/ ./policies/

# Create certs directory (will be mounted as volume in K8s)
RUN mkdir -p /app/certs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH=/root/.local/bin:$PATH

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 8000)); s.close()" || exit 1

# Run the application
CMD ["python", "-m", "src.main", "--host", "0.0.0.0", "--port", "8000"]

