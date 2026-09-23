FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose ports
EXPOSE 8002

# Default command (overridden by docker-compose.yml in this repo)
# Keep it aligned with the A2A FastAPI app so the image is usable standalone.
CMD ["uvicorn", "src.a2a_app:app", "--host", "0.0.0.0", "--port", "8002"]

