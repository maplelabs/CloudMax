"""
Knowledge Base Service API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import get_db_session, get_current_user
from src.server.models.api import KnowledgeBaseInfoResponse
from src.server.models.db import RunbookDBModel

router = APIRouter()


@router.get("/info")
async def get_knowledge_base_info(
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> KnowledgeBaseInfoResponse:
    """
    Get knowledge base information and statistics.

    Returns:
        - Total number of documents (runbooks) in the knowledge base
        - Total size of all documents in bytes
    """
    try:
        print(f"DEBUG: Getting knowledge base info for user: {current_user}")

        # Get total count of runbooks
        count_stmt = select(func.count(RunbookDBModel.id))
        count_result = await session.execute(count_stmt)
        total_documents = count_result.scalar() or 0

        # Get total size of all runbook content in bytes
        size_stmt = select(func.sum(RunbookDBModel.content_size_bytes))
        size_result = await session.execute(size_stmt)
        total_size_bytes = size_result.scalar() or 0

        print(f"DEBUG: Found {total_documents} documents, total size: {total_size_bytes} bytes")

        return KnowledgeBaseInfoResponse(
            total_documents=total_documents,
            size_bytes=total_size_bytes
        )

    except Exception as e:
        print(f"Error getting knowledge base info: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get knowledge base info: {str(e)}")
