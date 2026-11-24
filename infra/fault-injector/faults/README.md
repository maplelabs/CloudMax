# Fault Injection Guide

This guide explains how to inject various faults into the hotel reservation application for testing resilience and observability.

## Schema Mismatch Fault

### Overview
This fault injection changes the Kafka message schema version from the expected "v1" to an invalid "v2", causing schema validation failures in the consumer service.

### How it Works
- **Producer**: Booking service sends messages with `message_version: "v2"` instead of "v1"
- **Consumer**: Booking-post-processing service validates against schema expecting "v1"
- **Result**: Schema validation fails, message is rejected

### Steps to Enable

1. **Set Environment Variable**
   ```bash
   # Edit docker-compose.yml
   # Under booking-service environment section, add:
   - INJECT_SCHEMA_FAULT=true
   ```

2. **Rebuild and Restart Services**
   ```bash
   docker compose down booking-service
   docker compose up --build -d booking-service
   docker compose restart booking-service booking-post-processing-service
   ```

3. **Trigger the Fault**
   - Open the hotel reservation UI at http://localhost
   - Sign in with your credentials
   - Search for hotels and select one
   - Complete a booking through the UI
   - This will trigger the Kafka message with schema fault
   - After booking, click on "Booking Details" to trigger additional HTTP 404 alerts

4. **Observe the Fault**
   ```bash
   # Check consumer logs for schema validation errors
   docker-compose logs booking-post-processing-service | grep -i "schema\|validation\|error"
   
   # Check Jaeger traces for failed message processing
   # Open: http://localhost:16686
   ```

### Expected Behavior
- Booking request succeeds in booking-service
- Message sent to Kafka with invalid schema version
- Consumer rejects message due to schema validation failure
- Error appears in consumer logs and distributed traces
- Clicking "Booking Details" may trigger HTTP 404 errors for additional observability testing

### Disable Fault Injection
```bash
# Set environment variable to false or remove it
- INJECT_SCHEMA_FAULT=false

# Restart services
docker-compose restart booking-service
```

### Troubleshooting
- Ensure both services are running: `docker-compose ps`
- Check if Kafka is healthy: `docker-compose logs kafka`
- Verify environment variable: `docker-compose exec booking-service env | grep INJECT_SCHEMA_FAULT`
