FROM python:3.12-slim
RUN groupadd --system app && useradd --system --gid app --create-home app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY py_requirements.txt .
COPY wheels/ wheels/
RUN pip install --no-cache-dir -r py_requirements.txt
COPY src/ src/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && chown -R app:app /app
ENV PYTHONPATH=/app
USER app
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
