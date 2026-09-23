"""
Pydantic models for Runbook API endpoints.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .enums import Status
from .pagination_meta import PaginationMeta


class RunbookListRequest(BaseModel):
    """Request model for POST /runbooks (Request Body)"""
    # Pagination
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=10, ge=1, le=100, description="Items per page")

    # Search parameters (optional)
    search_string: Optional[str] = Field(default=None,
                                         description="Used as name-contains filter if semantic search is disabled else it is used for semantic search")
    semantic_search: bool = Field(default=False, description="Enable semantic/vector search")


class RunbookListItem(BaseModel):
    """Individual runbook item in the list response"""
    id: str = Field(description="Unique runbook identifier")
    name: str = Field(description="Runbook name/title")
    source_type: str = Field(description="Source of the runbook (file, confluence)")
    content_size_bytes: int = Field(description="Size of the runbook content in bytes")
    created_at: datetime = Field(description="When the runbook was created")
    updated_at: datetime = Field(description="When the runbook was last updated")
    # Optional fields for search results
    similarity_score: Optional[float] = Field(default=None, description="Similarity score (0.0-1.0) for search results")


class RunbookListResponse(BaseModel):
    """Response for runbook list endpoint"""
    runbooks: list[RunbookListItem] = Field(description="List of runbooks for current page")
    pagination: PaginationMeta = Field(description="Pagination information")


class RunbookDetailResponse(BaseModel):
    """Response for individual runbook detail"""
    id: str = Field(description="Unique runbook identifier")
    name: str = Field(description="Runbook name/title")
    created_at: datetime = Field(description="When the runbook was created")
    updated_at: datetime = Field(description="When the runbook was last updated")
    content: str = Field(description="Full markdown content of the runbook")


class RunbookUpdateRequest(BaseModel):
    """Request model for updating a runbook"""
    title: Optional[str] = Field(default=None, description="Updated title for the runbook")
    content: Optional[str] = Field(default=None, description="Updated markdown content")


class BulkUploadFileResult(BaseModel):
    """Result for a single file in bulk upload operation"""
    filename: str = Field(description="Original filename")
    status: str = Field(description="Upload status: 'success', 'error', 'skipped'")
    runbook_id: Optional[str] = Field(default=None, description="Created runbook ID if successful")
    runbook_name: Optional[str] = Field(default=None, description="Created runbook name if successful")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")


class BulkUploadResponse(BaseModel):
    """Complete response for bulk runbook upload operation"""
    total_files: int = Field(description="Total number of files processed")
    successful_uploads: int = Field(description="Number of successful uploads")
    failed_uploads: int = Field(description="Number of failed uploads")
    skipped_files: int = Field(description="Number of skipped files")
    file_results: list[BulkUploadFileResult] = Field(description="Detailed results for each file")
    summary: str = Field(description="Summary message")


class BulkDeleteRequest(BaseModel):
    """Request model for bulk delete operation"""
    runbook_ids: list[str] = Field(
        description="List of runbook IDs to delete",
        min_length=1,
        max_length=100
    )


class BulkDeleteResult(BaseModel):
    """Result for a single runbook in bulk delete operation"""
    runbook_id: str = Field(description="Runbook ID")
    runbook_title: str = Field(description="Runbook title")
    status: Status = Field(description="Delete status: success or error")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")

    @property
    def is_success(self) -> bool:
        """Check if deletion was successful"""
        return self.status == Status.SUCCESS


class BulkDeleteResponse(BaseModel):
    """Complete response for bulk delete operation"""
    total_requested: int = Field(description="Total number of runbooks requested for deletion")
    successful_deletes: int = Field(description="Number of successfully deleted runbooks")
    failed_deletes: int = Field(description="Number of failed deletions")
    results: list[BulkDeleteResult] = Field(description="Detailed results for each runbook")
    summary: str = Field(description="Summary message (e.g., 'Deleted 4/5 runbooks (1 failed)')")


# Confluence Integration Models

class ConfluenceImportRequest(BaseModel):
    """Request model for importing runbooks from Confluence (credentials from app_config)"""
    page_url: str = Field(description="URL of the Confluence page to import")
    include_children: bool = Field(default=False, description="Include child pages recursively")
    max_depth: int = Field(default=10, ge=1, le=20, description="Maximum depth for child page recursion")
    max_pages: int = Field(default=50, ge=1, le=100, description="Maximum number of pages to import")


class ConfluenceImportedPage(BaseModel):
    """Individual page result from Confluence import"""
    title: str = Field(description="Page title")
    runbook_id: str = Field(description="Created runbook ID")
    page_id: str = Field(description="Confluence page ID")
    url: str = Field(description="Confluence page URL")
    status: str = Field(description="Import status: 'success', 'error', 'updated'")
    error: Optional[str] = Field(default=None, description="Error message if import failed")
    embedding_status: Optional[str] = Field(default=None, description="Embedding generation status: 'success', 'failed', or None if not applicable")


class ConfluenceImportResponse(BaseModel):
    """Response for Confluence import operation"""
    parent_page: ConfluenceImportedPage = Field(description="Result for the parent page")
    child_pages: list[ConfluenceImportedPage] = Field(default_factory=list, description="Results for child pages")
    total_imported: int = Field(description="Total number of pages successfully imported")
    total_failed: int = Field(description="Total number of pages that failed to import")


class ConfluenceValidationRequest(BaseModel):
    """Request model for validating Confluence credentials"""
    base_url: str = Field(description="Confluence base URL")
    username: str = Field(description="Confluence username/email")
    api_token: str = Field(description="Confluence API token")


class ConfluenceValidationResponse(BaseModel):
    """Response for Confluence validation"""
    status: str = Field(description="Validation status: 'success' or 'error'")
    user: Optional[str] = Field(default=None, description="Authenticated user display name")
    error: Optional[str] = Field(default=None, description="Error message if validation failed")
