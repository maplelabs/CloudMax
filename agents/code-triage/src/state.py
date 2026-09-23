"""LangGraph state definitions for code triaging workflow"""

from typing import TypedDict, List, Optional, Dict, Any, Tuple


class CodeSnippet(TypedDict, total=False):
    """Normalized structure for retrieved code snippets.

    At minimum we track file path, content, and language. Additional
    metadata (e.g. extracted line ranges) may be present.
    """

    file_path: str
    content: str
    language: str


class TriageState(TypedDict):
    """State for the code triaging workflow"""
    
    # Input
    error_message: str
    stack_trace: str
    repository: str
    
    # Error Parser outputs
    error_type: Optional[str]
    language: Optional[str]
    file_hints: Optional[List[str]]
    line_hints: Optional[List[str]]
    search_strategy: Optional[str]
    needs_code: Optional[bool]
    severity: Optional[str]

    # Code Retrieval outputs
    code_snippets: Optional[List[CodeSnippet]]
    code_content: Optional[str]
    retrieval_attempt_count: Optional[int]
    retrieval_failures: Optional[List[Tuple[str, str]]]  # List of (file_path, reason) tuples
    
    # Code Analyzer outputs
    root_cause: Optional[str]
    affected_code: Optional[str]
    recommendations: Optional[List[str]]
    confidence: Optional[float]
    analysis_attempt_count: Optional[int]
    analysis_needs_more_code: Optional[bool]
    analysis_additional_file_hints: Optional[List[str]]
    
    # Routing decisions
    should_retrieve_code: Optional[bool]
    retrieval_action: Optional[str]
    analysis_action: Optional[str]

    # Routing fallback tracking
    routing_fallback_used: Optional[bool]
    routing_fallback_reason: Optional[str]

    # Final output
    status: str
    error_summary: Optional[Dict[str, Any]]
    warnings: Optional[List[str]]

