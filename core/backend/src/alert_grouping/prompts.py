"""LLM prompts and helpers for alert grouping."""

from typing import List, Optional

from .models import Alert


MAX_CONTEXT_ALERTS = 50
CONTEXT_LOOKBACK_HOURS = 2


GROUPING_SYSTEM_PROMPT = """You are an expert SRE analyzing alert correlation for incident management.

Your task: Determine if a NEW alert belongs to an EXISTING incident group OR should start a NEW incident group.

CRITICAL RULES:
1. Group alerts using ONLY the information present on the alerts themselves (labels such as service, job, namespace, cluster, env, component, instance, pod, region; any other labels; alert names/descriptions; payload; timestamps). No RCA field is available at grouping time.

2. Approximate "same incident" by inferring a likely shared root cause from those labels and descriptions. Prefer grouping alerts that share the same or closely related:
   - service / component (e.g. same `service`, `job`, `component`),
   - environment / cluster (e.g. `env`, `namespace`, `cluster`, `region`),
   - resource identifiers (e.g. database name, queue/topic, hostname/instance ID) present in labels or payload.

3. **Fallback for alerts with missing labels**: When alerts lack proper labels (empty service, instance, pod), use alert name and timing:
   - Exact same alert_name within 3 minutes: Consider grouping (likely same recurring issue)
   - Infrastructure keyword (Kafka, Database) followed by Application keyword (NGINX, API) within 5 minutes: Consider cascading pattern
   - Otherwise, prefer keeping alerts separate if uncertain

4. Do NOT split alerts into different groups **just because** they come from different services if labels/descriptions/payload clearly indicate a shared failure chain (for example, checkout errors immediately following payment-service errors that depend on the same database).

5. Treat clearly different environments or clusters (e.g. different `env` or `cluster` labels) as strong evidence of different incidents unless the payload/labels explicitly show a shared dependency.

6. Cascading failures across services should still be in the SAME group when labels/description/payload indicate dependency relationships.

7. If the alert fits an existing group, return "join_group"

8. If the alert should start a NEW incident (doesn't fit existing groups), return "create_new_group"

9. If uncertain or alert seems isolated, return "skip" - it will be retried later

Examples:
CORRECT: Database connection pool exhausted leads to Payment service errors leads to Checkout timeouts
   Result: ONE GROUP (clear dependency chain, all caused by DB issue)

CORRECT: "NGINX 5xx Errors" at 10:00 + "NGINX 5xx Errors" at 10:02 (empty labels)
   Result: ONE GROUP (identical alert, 2 min apart, same recurring issue)

CORRECT: "Kafka High Lag" at 10:00 + "API Timeouts" at 10:00:30
   Result: ONE GROUP (Kafka to API cascading, 30 sec apart)

WRONG: "Service A Memory" + "Service B Memory" (different services, no shared resource)

Return JSON:
{
  "action": "join_group" | "create_new_group" | "skip",
  "group_id": <id if join_group, null otherwise>,
  "group_name": <descriptive name if create_new_group, null otherwise>,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of your decision that references the labels/description/payload you used along with the reasoning for adding those particular alerts into the group"
}
"""


def create_batch_grouping_prompt(
    all_alerts: List[Alert], existing_groups: Optional[List[dict]] = None
) -> str:
    """
    Create a prompt for batch analysis of all alerts to determine groupings.

    Args:
        all_alerts: List of ALL alerts to analyze
        existing_groups: Optional list of existing groups with structure:
            [{"group_name": "...", "alert_ids": [...], "confidence": 0.9, "reasoning": "..."}]

    Returns:
        Formatted prompt string
    """
    import json

    # Format all alerts
    alerts_data = []
    for alert in all_alerts:
        alerts_data.append(
            {
                "alert_id": alert.id,
                "alert_name": alert.alert_name,
                "severity": alert.severity.value,
                "status": alert.status,
                "timestamp": alert.starts_at.isoformat(),
                "labels": alert.labels or {},
                "annotations": alert.annotations or {},
            }
        )

    # Build existing groups section
    existing_groups_section = ""
    if existing_groups:
        existing_groups_section = f"""
EXISTING INCIDENT GROUPS ({len(existing_groups)} groups):
================================================================
{json.dumps(existing_groups, indent=2)}

"""

    # Build task description based on whether we have existing groups
    if existing_groups:
        task_description = """TASK:
=====
Analyze ALL the alerts above in the context of EXISTING incident groups.

For each alert, determine if it should:
1. **ADD TO EXISTING GROUP**: If the alert matches an existing group's resource identifiers (same container, pod, instance)
2. **CREATE NEW GROUP**: If the alert represents a new incident not covered by existing groups
3. **REMAIN UNGROUPED**: If the alert is a test/notification or doesn't correlate with anything

CRITICAL RULES FOR ADDING TO EXISTING GROUPS:
- The alert MUST share the SAME resource identifiers (container_id, container_name, pod, instance, service) as alerts already in that group
- If an alert affects the SAME container/pod as an existing group, it MUST be added to that group (cascading failure)
- Container restarts, memory issues, errors on the SAME resource = SAME GROUP
- DO NOT add alerts to a group just because they have similar alert names - they must target the SAME resource

CRITICAL RULES FOR CREATING NEW GROUPS:
- Only create a new group if you can identify at least 2 alerts that belong together
- The alerts must share the SAME resource identifiers (same container_id, container_name, pod, instance)
- ALL alerts affecting the SAME resource MUST be in ONE group (e.g., memory + restart on same container = ONE group)
- Single alerts that don't match existing groups should go to ungrouped_alert_ids

**Fallback for alerts with missing labels**: When alerts lack proper labels:
- Exact same alert_name within 3 minutes: Consider grouping (same recurring issue)
- Infrastructure keyword (Kafka, Database, RabbitMQ) then Application keyword (NGINX, API) within 5 minutes: Consider cascading
- Otherwise keep separate if uncertain"""
    else:
        task_description = """TASK:
=====
Analyze ALL the alerts above and determine how they should be grouped into incident groups.

CRITICAL: Group alerts together if they:
1. Share the SAME resource identifiers (e.g., same container_id, container_name, pod, instance, service in labels)
2. Represent a cascading failure or related symptoms on the SAME resource
   - Example: High memory + Memory growth + Container restart on the SAME container = ONE GROUP (single incident)
   - Example: Database errors + Connection pool exhaustion on the SAME database = ONE GROUP
   - Example: Service errors + Pod restarts on the SAME pod = ONE GROUP
3. Have temporal correlation AND affect the same resource (alerts within minutes of each other on the same container/pod/service)

IMPORTANT GROUPING RULES:
- If alerts share the SAME container_id, container_name, or pod name, they MUST be in the SAME group (they are part of the same incident)
- Container restarts, OOM kills, memory issues, CPU spikes on the SAME resource = ONE GROUP
- Different alert types (memory, restart, error) on the SAME resource = ONE GROUP (cascading failure)
- Only separate alerts into different groups if they affect DIFFERENT resources (different containers, pods, instances)

**Fallback for alerts with missing labels**: When alerts lack proper labels:
- Exact same alert_name within 3 minutes: Consider grouping
- Infrastructure keyword (Kafka, Database) then Application keyword (NGINX, API) within 5 minutes: Consider cascading
- Otherwise keep separate if uncertain

DO NOT group alerts that:
- Are test alerts or notifications
- Fire more than 5 minutes apart (unless exact same alert_name)
- Are from different environments/clusters
- Are semantically unrelated"""

    prompt = f"""
ANALYZE ALL ALERTS AND DETERMINE GROUPINGS
===========================================

ALL CURRENT ALERTS IN SYSTEM ({len(alerts_data)} total alerts):
================================================================
{json.dumps(alerts_data, indent=2)}

{existing_groups_section}
{task_description}

RESPONSE FORMAT:
================
Process each alert IN ORDER and return a JSON object with per-alert decisions:

{{
  "decisions": [
    {{
      "alert_id": "alert-123",
      "action": "create_new_group",  // or "join_group" or "skip"
      "temp_group_id": 1,  // only for create_new_group - assign sequential IDs (1, 2, 3...)
      "group_id": null,  // only for join_group action - use temp_group_id for newly created groups
      "group_name": "Descriptive incident name",  // only for create_new_group action
      "confidence": 0.95,
      "reasoning": "Brief explanation referencing specific shared resource identifiers"
    }},
    {{
      "alert_id": "alert-124",
      "action": "join_group",
      "temp_group_id": null,
      "group_id": 1,  // Reference the temp_group_id from the group created above
      "group_name": null,
      "confidence": 0.98,
      "reasoning": "Same container_id as previous alert - cascading failure"
    }}
  ]
}}

CRITICAL RULES:
- Process alerts IN THE ORDER they appear in the list above
- When you create a new group with "create_new_group", assign it a temp_group_id (1, 2, 3, etc.)
- Subsequent alerts can join groups you just created by using "join_group" with the temp_group_id
- If alerts share the SAME resource identifiers (container_id, pod, instance), they MUST be in the SAME group
- Example: Alert 1 (memory issue on container X) should create_new_group (temp_group_id=1)
           Alert 2 (restart on container X) should join_group (group_id=1)
- Use "skip" action only for test alerts or alerts that do not correlate with anything
"""

    return prompt


def format_labels(labels: dict) -> str:
    """Format labels dictionary for display."""
    if not labels:
        return "{}"
    items = [f"{k}={v}" for k, v in labels.items()]
    return "{" + ", ".join(items) + "}"


def format_annotations(annotations: dict) -> str:
    """Format annotations dictionary for display."""
    if not annotations:
        return "{}"
    items = []
    for k, v in annotations.items():
        v_str = str(v)
        if len(v_str) > 100:
            v_str = v_str[:97] + "..."
        items.append(f"{k}={v_str}")
    return "{" + ", ".join(items) + "}"


def format_group_alerts(alerts: List[Alert]) -> str:
    """Format list of alerts for display."""
    if not alerts:
        return "  (no alerts)"

    lines = []
    for alert in alerts:
        lines.append(
            f"  - {alert.alert_name} ({alert.severity.value}) at {alert.starts_at.isoformat()}"
        )
        if alert.labels:
            service = alert.labels.get("service", alert.labels.get("job", "N/A"))
            env = alert.labels.get("environment", alert.labels.get("env", "N/A"))
            lines.append(f"    service={service}, env={env}")

    return "\n".join(lines)
