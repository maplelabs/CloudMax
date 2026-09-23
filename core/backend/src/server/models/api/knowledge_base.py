from pydantic import BaseModel, Field


class KnowledgeBaseInfoResponse(BaseModel):
    """Response for knowledge base information"""
    total_documents: int = Field(description="Total number of documents in the knowledge base")
    size_bytes: int = Field(description="Total size of all documents in bytes")
