FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY py_requirements.txt .
COPY wheels/ wheels/
RUN pip install --no-cache-dir -r py_requirements.txt
COPY src/ src/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
ENV PYTHONPATH=/app
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
