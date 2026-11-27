# Alert Type:

**Docker Container Restart:**
```promql
resets(container_cpu_usage_seconds_total{container_label_com_docker_compose_service=~".*",cpu="total"}[5m]) > 0
```

**Rapid Memory Growth:**
```promql
rate(container_memory_usage_bytes{container_label_com_docker_compose_service=~".*"}[5m]) > 1000000
```

**High Memory Usage:**
```promql
container_memory_usage_bytes{container_label_com_docker_compose_service=~".*"} > 500000000
```

# Description:
This alert is generated when a container restarts unexpectedly, shows rapid memory growth, or exceeds memory usage thresholds. The steps in this runbook cover triaging and diagnostic steps for container memory and stability issues.

## General Health Checks

### Container Health
- Check from Container Performance Dashboard in Hotel Monitoring folder in Grafana if CPU and memory usage of the affected container is less than 80% of total memory available
- Check if there are continuous container restarts
- Check container uptime and restart count

### Spike in Traffic
- Check Nginx Performance Dashboard in Hotel Monitoring folder in Grafana if active connections is more than 1000 which can cause load
- Check if there is unusual spike in API requests

## Steps to Identify the Issue

### Identify Affected Container and Memory Pattern
- Check from Container Performance Dashboard in Hotel Monitoring folder in Grafana which container has restarted or has high memory usage in the last 20 minutes (10 mins before and 10 mins after the alert)
- Get the container restart count, last restart timestamp, current memory usage (%), and CPU usage from Container Performance Dashboard
- Analyze memory growth pattern - steadily increasing (memory leak), saw-tooth pattern (OOM crash and restart), or stable with sudden spike (traffic triggered)
- Check if memory is being released over time or continuously growing

### Check Traffic and API Correlation
- Check from Nginx Performance Dashboard in Hotel Monitoring folder in Grafana if active connections spiked above 1000 or if there is unusual API request rate increase in the last 20 minutes (10 mins before and 10 mins after the alert)
- Check from Nginx Performance Dashboard if there are any 5xx errors from the affected service correlating with memory growth or restarts
- Get the API request count and response times from Nginx Performance Dashboard to correlate with memory growth pattern

### Check Service Dependencies (if applicable)
- If affected service uses database, check from Postgres Performance Dashboard in Hotel Monitoring folder in Grafana for connection pool status, cache hit ratio, transaction failures, or database locks in the last 20 minutes
- If affected service uses Kafka, check from Kafka Performance Dashboard in Hotel Monitoring folder in Grafana for consumer lag, producer errors, or DLQ message count in the last 20 minutes
- Check if dependent services are running and healthy from Container Performance Dashboard

### Check Application Logs for Errors
- Check from Hotel Service Logs Dashboard in Hotel Monitoring folder in Grafana for the affected container logs in the last 20 minutes (10 mins before and 10 mins after the alert)
- Look for out-of-memory errors, heap space errors, memory-related exceptions, connection errors to external dependencies, or application stack traces

## Collate all results and share the final findings and conclusion

**repository:** jathin-s-ML/fault-injector
