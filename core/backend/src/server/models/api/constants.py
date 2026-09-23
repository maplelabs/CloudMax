"""
Constants for API models - contains default values and configuration constants.
For type definitions, see enums.py
"""
from .enums import Severity, Timeline

# Default values
DEFAULT_SEVERITY = Severity.P1
DEFAULT_TIMELINE = Timeline.ONE_HOUR
DEFAULT_PAGE_SIZE = 10
DEFAULT_MAX_PAGE_SIZE = 100

# API Configuration
DEFAULT_API_VERSION = "2023-12-01-preview"
DEFAULT_ALERT_SOURCE = "grafana"

# Validation limits
MIN_CONFIDENCE_SCORE = 0
MAX_CONFIDENCE_SCORE = 10
MIN_EVALUATION_SCORE = 0
MAX_EVALUATION_SCORE = 10
MIN_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
MIN_RETRIES = 1
MAX_RETRIES = 5

# Timeline limits
MAX_CUSTOM_RANGE_DAYS = 90  # Maximum allowed days for custom time ranges
