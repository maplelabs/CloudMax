"""
Alert Grouping and Triage Constants

System-wide hardcoded values that should not be configurable via UI/API.
"""

# ==============================================================================
# WORKER TIMEOUTS (seconds)
# ==============================================================================

BATCH_GROUPING_TIMEOUT_SEC = 600
UNGROUPED_RETRY_TIMEOUT_SEC = 600


# ==============================================================================
# KNOWLEDGE BASE RAG
# ==============================================================================

KNOWLEDGE_BASE_MAX_DOCUMENTS = 5      # Max runbooks per search (reduced from 7)
KNOWLEDGE_BASE_MIN_SIMILARITY = 0.50  # Min cosine similarity threshold (0.0-1.0)


# ==============================================================================
# ALERT GROUP CONTEXT
# ==============================================================================

MAX_ALERTS_PER_GROUP_SAMPLE = 5       # Max alerts for group summaries


# ==============================================================================
# RETRY CONFIGURATION
# ==============================================================================

GROUPING_FAILURE_RETRY_ATTEMPTS = 3
GROUPING_FAILURE_RETRY_DELAY_SECONDS = 60
