from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    current_page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    total_items: int = Field(description="Total number of items")
