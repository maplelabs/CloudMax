"""
Alert Grouping Module

This module contains the LLM-based alert grouping logic that reads alerts
from the alerts folder and groups them based on correlation patterns.

Directory Structure:
- models.py: Data models for alerts and grouping decisions
- prompts.py: LLM prompts for grouping analysis
- services/: Alert grouping and group triage services
"""

from .models import AlertGroup, GroupingDecision

__all__ = ["AlertGroup", "GroupingDecision"]
