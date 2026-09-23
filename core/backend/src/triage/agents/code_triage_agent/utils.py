"""
Utility functions for Code Triage Agent
"""

import re
from typing import Optional


def validate_repository_format(repo: str) -> bool:
    """
    Validate repository format: owner/repo
    
    Args:
        repo: Repository string to validate
        
    Returns:
        True if valid format, False otherwise
    """
    pattern = r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$'
    return bool(re.match(pattern, repo))


def normalize_repository(repo: str) -> Optional[str]:
    """
    Normalize repository from various formats to owner/repo format.
    
    Handles:
    - https://github.com/owner/repo → owner/repo
    - git@github.com:owner/repo.git → owner/repo
    - owner/repo → owner/repo
    
    Args:
        repo: Repository string in various formats
        
    Returns:
        Normalized repository string or None if invalid
    """
    if not repo:
        return None
    
    # Remove https://github.com/ prefix
    if repo.startswith("https://github.com/"):
        repo = repo.replace("https://github.com/", "")
    
    # Remove git@github.com: prefix
    if repo.startswith("git@github.com:"):
        repo = repo.replace("git@github.com:", "")
    
    # Remove .git suffix
    if repo.endswith(".git"):
        repo = repo[:-4]
    
    # Remove trailing slash
    repo = repo.rstrip("/")
    
    # Validate format
    if validate_repository_format(repo):
        return repo
    
    return None

