"""Pydantic models for Code Triage Agent."""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class RepositoryInfo(BaseModel):
    """Extracted repository information"""
    repository: str = Field(description="Repository in format owner/repo")
    confidence: float = Field(description="Confidence score 0.0-1.0")
    source: str = Field(description="Where it was found (metadata/content)")


class CodeTriageRequest(BaseModel):
    """
    Request to code-triage service.

    Note: GitHub token is configured via environment variable in the
    code-triage-agent service, not passed in the request.
    """
    error: str
    repository: str


class CodeSnippet(BaseModel):
    """Code snippet from analysis"""
    file_path: str
    content: str
    language: str = "python"
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class CodeTriageResponse(BaseModel):
    """Response from code-triage service."""

    status: Literal["success", "error", "timeout", "completed"]
    root_cause: Optional[str] = None
    code_snippets: List[CodeSnippet] = Field(default_factory=list)
    suggested_fixes: List[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    def is_success(self) -> bool:
        """Return True if the analysis completed successfully."""
        return self.status in ("completed", "success")

