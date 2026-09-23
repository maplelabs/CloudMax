"""
Runbook Manager Service API endpoints.
"""

import json
import logging
from datetime import datetime as dt, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import get_current_user, get_db_session
from src.server.async_workers.confluence_sync_job import enqueue_confluence_sync_now
from src.server.models.api.enums import Status
from src.server.models.api.pagination_meta import PaginationMeta
from src.server.models.api.runbooks import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkDeleteResult,
    BulkUploadFileResult,
    BulkUploadResponse,
    ConfluenceImportedPage,
    ConfluenceImportRequest,
    ConfluenceImportResponse,
    ConfluenceValidationRequest,
    ConfluenceValidationResponse,
    RunbookDetailResponse,
    RunbookListItem,
    RunbookListRequest,
    RunbookListResponse,
    RunbookUpdateRequest,
)
from src.server.models.db import AppConfigDBModel, RunbookDBModel, UserDBModel
from src.server.services.confluence import ConfluenceService
from src.server.utilities.embedding_manager import get_embedding_manager_async

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
MAX_BULK_UPLOAD_FILES = 50
SUPPORTED_FILE_EXTENSIONS = ('.md', '.txt')


# Helper functions

async def _get_app_config(session: AsyncSession) -> 'AppConfigDBModel':
    """Retrieve app configuration from database."""
    from src.server.models.db import AppConfigDBModel

    stmt = select(AppConfigDBModel).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _validate_app_config_exists(app_config: AppConfigDBModel | None) -> None:
    """Validate that app config exists and has external runbook config."""
    if not app_config or not app_config.external_runbook_config:
        raise HTTPException(
            status_code=400,
            detail="Confluence not configured. Please configure Confluence in Setup page first."
        )


def _validate_confluence_enabled(confluence_config: dict | None) -> None:
    """Validate that Confluence integration is enabled."""
    if not confluence_config or not confluence_config.get('enabled'):
        raise HTTPException(
            status_code=400,
            detail="Confluence integration not enabled. Please enable it in Setup page first."
        )


def _extract_confluence_credentials(confluence_config: dict) -> dict:
    """Extract and validate Confluence credentials from config."""
    config = {
        'base_url': confluence_config.get('base_url', '').rstrip('/'),
        'username': confluence_config.get('username'),
        'api_token': confluence_config.get('api_token')
    }

    if not all(config.values()):
        raise HTTPException(
            status_code=400,
            detail="Incomplete Confluence configuration. Please check Setup page."
        )

    return config


async def _get_confluence_config(session: AsyncSession) -> dict:
    """
    Retrieve Confluence configuration from app_config.

    Args:
        session: Database session

    Returns:
        Dictionary with base_url, username, api_token

    Raises:
        HTTPException: If configuration is missing or incomplete
    """
    app_config = await _get_app_config(session)
    _validate_app_config_exists(app_config)

    confluence_config = app_config.external_runbook_config.get('confluence')
    _validate_confluence_enabled(confluence_config)

    return _extract_confluence_credentials(confluence_config)


def _normalize_embedding_vector(embedding: any) -> list[float]:
    """
    Normalize embedding vector to a list of floats for pgvector.

    The embedding model may return various formats (list, numpy array, or JSON string).
    This function ensures we always get a list[float] suitable for PostgreSQL pgvector.

    Args:
        embedding: Raw embedding output from embedding model

    Returns:
        List of float values

    Raises:
        ValueError: If embedding format is invalid or contains non-numeric values
    """
    if isinstance(embedding, str):
        try:
            embedding = json.loads(embedding)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("Invalid embedding: expected JSON array, got string")

    if hasattr(embedding, '__iter__') and not isinstance(embedding, str):
        embedding = list(embedding)

    if not isinstance(embedding, (list, tuple)) or not embedding:
        raise ValueError(f"Invalid embedding: expected non-empty list, got {type(embedding)}")

    try:
        return [float(x) for x in embedding]
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid embedding values: all elements must be numeric - {e}")


async def _generate_and_validate_embedding(content: str, context: str) -> list[float]:
    """
    Generate and validate embedding for content.

    Args:
        content: Text to embed
        context: Description for error messages (e.g., runbook title)

    Returns:
        Normalized embedding vector

    Raises:
        HTTPException: If embedding generation or validation fails
    """
    try:
        embedding_manager = await get_embedding_manager_async()
        embedding_model = embedding_manager.get_embedding_model()
        raw_embedding = await embedding_model.aembed_query(content)
        return _normalize_embedding_vector(raw_embedding)
    except ValueError as e:
        logger.error(f"Embedding validation failed for '{context}': {e}")
        raise HTTPException(status_code=500, detail=f"Invalid embedding format: {e}")
    except Exception as e:
        logger.error(f"Embedding generation failed for '{context}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate embedding: {e}")


async def _perform_semantic_search(
        request: RunbookListRequest,
        db: AsyncSession,
        user: str
) -> RunbookListResponse:
    """Perform semantic/vector search and return results in list format."""
    try:
        logger.info(f"User {user} performing semantic search for: '{request.search_string}'")

        # Generate and normalize embedding for search query
        embedding_manager = await get_embedding_manager_async()
        embedding_model = embedding_manager.get_embedding_model()
        query_embedding = await embedding_model.aembed_query(request.search_string)
        query_embedding_list = _normalize_embedding_vector(query_embedding)

        # Vector similarity query using pgvector methods
        sql_query = select(
            RunbookDBModel.id,
            RunbookDBModel.title,
            RunbookDBModel.source_type,
            RunbookDBModel.content,
            RunbookDBModel.content_size_bytes,
            RunbookDBModel.created_at,
            RunbookDBModel.updated_at,
            RunbookDBModel.embedding.cosine_distance(query_embedding_list).label('distance')
        ).where(
            RunbookDBModel.embedding.is_not(None)
        ).order_by(
            RunbookDBModel.embedding.cosine_distance(query_embedding_list)
        ).limit(request.page_size).offset((request.page - 1) * request.page_size)

        result = await db.execute(sql_query)
        runbooks_data = result.fetchall()

        # Convert to response format
        runbooks = []
        for row in runbooks_data:
            runbooks.append(RunbookListItem(
                id=str(row.id),
                name=row.title,
                source_type=row.source_type,
                content_size_bytes=row.content_size_bytes,
                created_at=row.created_at,
                updated_at=row.updated_at,
                similarity_score=1.0 - row.distance if row.distance is not None else 0.0
            ))

        # Get total count for pagination
        count_query = select(func.count(RunbookDBModel.id))
        count_result = await db.execute(count_query)
        total_items = count_result.scalar() or 0

        return RunbookListResponse(
            runbooks=runbooks,
            pagination=PaginationMeta(
                current_page=request.page,
                page_size=request.page_size,
                total_items=total_items
            )
        )

    except Exception:

        logger.exception(f"Semantic search failed")
        raise HTTPException(status_code=500, detail=f"Semantic search failed")


async def _perform_database_query(
        request: RunbookListRequest,
        db: AsyncSession,
        user: str
) -> RunbookListResponse:
    """Perform database query with optional text search and return paginated results."""
    try:
        # Build base query
        query = select(RunbookDBModel)
        count_query = select(func.count(RunbookDBModel.id))

        # Apply search conditions if search string provided
        if request.search_string:
            search_conditions = [
                RunbookDBModel.title.ilike(f"%{request.search_string}%"),
                RunbookDBModel.content.ilike(f"%{request.search_string}%")
            ]
            search_filter = or_(*search_conditions)
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Apply pagination and ordering
        query = query.order_by(RunbookDBModel.created_at.desc())
        query = query.limit(request.page_size).offset((request.page - 1) * request.page_size)

        # Execute queries
        result = await db.execute(query)
        runbooks_data = result.scalars().all()

        count_result = await db.execute(count_query)
        total_items = count_result.scalar() or 0

        # Convert to response format
        runbooks = []
        for runbook in runbooks_data:
            runbooks.append(RunbookListItem(
                id=str(runbook.id),
                name=runbook.title,
                source_type=runbook.source_type,
                content_size_bytes=runbook.content_size_bytes,
                created_at=runbook.created_at,
                updated_at=runbook.updated_at
            ))

        return RunbookListResponse(
            runbooks=runbooks,
            pagination=PaginationMeta(
                current_page=request.page,
                page_size=request.page_size,
                total_items=total_items
            )
        )

    except Exception as e:
        logger.exception(f"Database query failed")
        raise HTTPException(status_code=500, detail=f"Query failed")


async def _check_duplicate_runbook(title: str, session: AsyncSession) -> RunbookDBModel | None:
    """
    Check if a runbook with the given title already exists.

    Args:
        title: The title to check for duplicates
        session: Database session

    Returns:
        Existing runbook if found, None otherwise
    """
    logger.info(f"Checking for existing runbook with name: {title}")
    existing_query = select(RunbookDBModel).where(RunbookDBModel.title == title)
    existing_result = await session.execute(existing_query)
    return existing_result.scalars().first()


async def _extract_title_from_filename(filename: str) -> str:
    """
    Extract title from filename by removing extension.

    Args:
        filename: The filename to process

    Returns:
        Title extracted from filename
    """
    # Use rsplit to handle filenames with multiple dots correctly
    title = filename.rsplit('.', 1)[0]
    return title.strip() if title else "Untitled Runbook"


async def _process_runbook_request(
        request: RunbookListRequest,
        db: AsyncSession,
        user: str
) -> RunbookListResponse:
    """Process runbook request and route to appropriate handler."""
    try:
        logger.info(f"Processing runbook request, page: {request.page}")

        # Route to appropriate handler based on search type
        if request.search_string and request.semantic_search:
            # Semantic/Vector Search - uses embeddings and similarity
            logger.info(f"Performing semantic search for: '{request.search_string}'")
            return await _perform_semantic_search(request, db, user)
        else:
            # Database Query - handles both text search and regular listing
            if request.search_string:
                logger.info(f"Performing text search for: '{request.search_string}'")
            else:
                logger.info("Fetching paginated runbook list")
            return await _perform_database_query(request, db, user)

    except Exception:

        logger.exception(f"Failed to process runbook request")
        raise HTTPException(status_code=500, detail=f"Failed to process request")


@router.get("")
async def list_runbooks(
        request: RunbookListRequest = Depends(),
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> RunbookListResponse:
    """
    List all runbooks with pagination and search parameters.

    Supports both text search and semantic search with pgvector.

    Args:
        request: Pagination and search parameters
        session: Database session from dependency
    """
    return await _process_runbook_request(request, session, current_user)


@router.get("/{id}")
async def get_runbook(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> RunbookDetailResponse:
    """
    Get specific runbook by ID.

    Retrieves full runbook details including content from PostgreSQL.

    Args:
        id: Runbook identifier
        session: Database session from dependency
    """
    try:
        logger.info(f"Fetching runbook with ID: {id}")

        # Query runbook by database ID
        query = select(RunbookDBModel).where(RunbookDBModel.id == int(id))
        result = await session.execute(query)
        runbook = result.scalar_one_or_none()

        if not runbook:
            logger.warning(f"Runbook not found: {id}")
            raise HTTPException(status_code=404, detail=f"Runbook with ID '{id}' not found")

        logger.info(f"Successfully retrieved runbook: {runbook.title}")

        return RunbookDetailResponse(
            id=str(runbook.id),
            name=runbook.title,
            created_at=runbook.created_at,
            updated_at=runbook.updated_at,
            content=runbook.content
        )

    except HTTPException:

        raise

    except Exception:

        logger.exception(f"Failed to fetch runbook {id}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch runbook")


@router.post("")
async def create_runbooks(
        files: list[UploadFile] = File(..., description="Upload one or multiple files"),
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> BulkUploadResponse:
    """
    Create runbook(s) from uploaded files (handles both single and multiple files).

    The filename (without extension) is automatically used as the runbook title.

    Processes markdown/text files, generates embeddings, and stores in PostgreSQL.

    Args:
        files: List of uploaded files (can be single or multiple)
        session: Database session from dependency
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be provided")

    logger.info(f"Processing upload with {len(files)} file(s)")
    return await _handle_bulk_upload(files, session)


async def _process_single_file_core(
        file: UploadFile,
        session: AsyncSession
) -> RunbookDBModel:
    """
    Core logic for processing a single file upload.
    Returns the created runbook model or raises appropriate exceptions.
    """
    logger.info(f"Creating runbook from uploaded file: {file.filename}")

    # Validate file type
    if not file.filename or not file.filename.endswith(SUPPORTED_FILE_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(SUPPORTED_FILE_EXTENSIONS)} files are supported"
        )

    # Read file content
    try:
        content_bytes = await file.read()
        markdown_content = content_bytes.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text")

    if not markdown_content.strip():
        raise HTTPException(status_code=400, detail="File content cannot be empty")

    # Use filename (without extension) as title
    final_title = await _extract_title_from_filename(file.filename)

    # Check if runbook with this name already exists
    existing_runbook = await _check_duplicate_runbook(final_title, session)
    if existing_runbook:
        logger.info(f"Runbook with name '{final_title}' already exists (ID: {existing_runbook.id}). Skipping upload.")
        raise HTTPException(
            status_code=409,
            detail=f"Runbook with name '{final_title}' already exists (ID: {existing_runbook.id}). Upload skipped to prevent duplicates."
        )

    # Generate embedding
    logger.info(f"Generating embedding for runbook: {final_title}")
    embedding_vector = await _generate_and_validate_embedding(markdown_content, final_title)

    # Create runbook record
    try:
        new_runbook = RunbookDBModel(
            title=final_title,
            content=markdown_content,
            content_size_bytes=len(markdown_content.encode('utf-8')),
            embedding=embedding_vector
        )

        session.add(new_runbook)
        await session.commit()
        await session.refresh(new_runbook)
    except IntegrityError as e:
        await session.rollback()
        logger.error(f"Database operation failed: {str(e)}")
        raise HTTPException(status_code=409, detail="Runbook with similar content already exists")
    except Exception as e:
        await session.rollback()
        logger.error(f"Database operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    logger.info(f"Successfully created runbook: {final_title} (ID: {new_runbook.id})")
    return new_runbook


async def _handle_bulk_upload(
        files: list[UploadFile],
        session: AsyncSession
) -> BulkUploadResponse:
    """Handle bulk file upload and return bulk response"""
    if len(files) > MAX_BULK_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BULK_UPLOAD_FILES} files allowed per bulk upload"
        )

    logger.info(f"Processing bulk upload of {len(files)} files")

    results = []
    successful_uploads = 0
    failed_uploads = 0
    skipped_files = 0

    # Process each file individually
    for file in files:
        result = await _process_single_file_upload(file, session)
        results.append(result)

        if result.status == "success":
            successful_uploads += 1
        elif result.status == "failed":
            failed_uploads += 1
        elif result.status == "skipped":
            skipped_files += 1

    # Generate summary message
    summary = f"Processed {len(files)} files: {successful_uploads} successful, {failed_uploads} failed, {skipped_files} skipped"

    logger.info(f"Bulk upload completed: {summary}")

    return BulkUploadResponse(
        total_files=len(files),
        successful_uploads=successful_uploads,
        failed_uploads=failed_uploads,
        skipped_files=skipped_files,
        file_results=results,
        summary=summary
    )


async def _process_single_file_upload(
        file: UploadFile,
        session: AsyncSession
) -> BulkUploadFileResult:
    """
    Process a single file upload and return the result for bulk upload.
    Uses the same core logic as single upload but returns BulkUploadFileResult.

    Args:
        file: The uploaded file to process
        session: Database session

    Returns:
        BulkUploadFileResult with the processing result
    """
    try:
        # Use the core single file processing logic
        new_runbook = await _process_single_file_core(file, session)

        return BulkUploadFileResult(
            filename=file.filename,
            status="success",
            runbook_id=str(new_runbook.id),
            runbook_name=new_runbook.title
        )

    except HTTPException as e:
        # Duplicates are skipped
        if e.status_code == 409:
            return BulkUploadFileResult(
                filename=file.filename,
                status="skipped",
                error_message=e.detail
            )

        # All other HTTP errors are treated as failed
        return BulkUploadFileResult(
            filename=file.filename,
            status="failed",
            error_message=e.detail
        )

    except Exception as e:
        # Handle any other unexpected errors
        logger.error(f"Unexpected error processing {file.filename}: {str(e)}")
        return BulkUploadFileResult(
            filename=file.filename,
            status="failed",
            error_message=f"Unexpected error: {str(e)}"
        )


@router.put("/{id}")
async def update_runbook(
        id: str,
        request: RunbookUpdateRequest,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
):
    """
    Update an existing runbook's title and content.

    Args:
        id: Database ID of the runbook to update
        request: Update request with title and/or content
        session: Database session from dependency

    Returns:
        RunbookDetailResponse: Updated runbook details
    """
    try:
        # Validate request has at least one field to update
        if not any([request.title, request.content]):
            raise HTTPException(
                status_code=400,
                detail="At least one field (title, content) must be provided for update"
            )

        logger.info(f"Updating runbook '{id}'")

        # Check if runbook exists
        query = select(RunbookDBModel).where(RunbookDBModel.id == int(id))
        result = await session.execute(query)
        existing_runbook = result.scalar_one_or_none()

        if not existing_runbook:
            raise HTTPException(
                status_code=404,
                detail=f"Runbook with ID '{id}' not found"
            )

        # Prepare update data
        update_data = {}

        if request.title is not None:
            if len(request.title.strip()) == 0:
                raise HTTPException(
                    status_code=422,
                    detail="Title cannot be empty"
                )
            update_data['title'] = request.title.strip()

        if request.content is not None:
            if len(request.content.strip()) == 0:
                raise HTTPException(
                    status_code=422,
                    detail="Content cannot be empty"
                )
            update_data['content'] = request.content
            update_data['content_size_bytes'] = len(request.content.encode('utf-8'))

            embedding = await _generate_embedding(request.content, f"runbook {id}")
            if embedding:
                update_data['embedding'] = embedding
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate embedding for updated content"
                )

        # Update in database
        try:
            update_query = update(RunbookDBModel).where(RunbookDBModel.id == int(id)).values(**update_data)
            await session.execute(update_query)
            await session.commit()

        except Exception:
            await session.rollback()
            logger.exception(f"Failed to update runbook in database")
            raise HTTPException(
                status_code=500,
                detail="Failed to update runbook in database"
            )

        logger.info(f"Successfully updated runbook: {id}")
        return {"status": "success", "message": f"Runbook {id} updated"}

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Failed to update runbook {id}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.delete("/{id}")
async def delete_runbook(
        id: str,
        current_user: UserDBModel = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
):
    """
    Delete runbook.

    Requires authentication - only logged-in users can delete runbooks.
    Removes runbook and associated embeddings from PostgreSQL.

    Args:
        id: Runbook identifier to delete
        current_user: Authenticated user from JWT token
        session: Database session from dependency
    """
    # Verify user is authenticated (get_current_user already enforces this)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        logger.info(f"User {current_user.username} (ID: {current_user.id}) deleting runbook with ID: {id}")

        # Check if runbook exists
        query = select(RunbookDBModel).where(RunbookDBModel.id == int(id))
        result = await session.execute(query)
        runbook = result.scalar_one_or_none()

        if not runbook:
            logger.warning(f"Runbook not found for deletion: {id}")
            raise HTTPException(status_code=404, detail=f"Runbook with ID '{id}' not found")

        # Delete the runbook
        await session.delete(runbook)
        await session.commit()

        logger.info(f"Successfully deleted runbook: {runbook.title} (ID: {id})")

        return {"status": "success", "message": f"Runbook {id} deleted"}

    except HTTPException:
        raise

    except Exception:
        await session.rollback()
        logger.exception(f"Failed to delete runbook {id}")
        raise HTTPException(status_code=500, detail=f"Failed to delete runbook")


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_runbooks(
        request: BulkDeleteRequest,
        current_user: UserDBModel = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> BulkDeleteResponse:
    """
    Delete multiple runbooks in a single operation.

    Requires authentication - only logged-in users can perform bulk deletions.
    Uses a bulk delete helper to perform efficient batch deletion within a single transaction.
    Continues processing even if some deletions fail (partial success allowed).
    """
    # Verify user is authenticated (get_current_user already enforces this)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    logger.info(f"User {current_user.username} (ID: {current_user.id}) initiating bulk delete of {len(request.runbook_ids)} runbooks")

    results = await _bulk_delete_runbooks_helper(request.runbook_ids, session)

    successful_deletes = sum(1 for r in results if r.is_success)
    failed_deletes = len(results) - successful_deletes

    summary = f"Deleted {successful_deletes}/{len(request.runbook_ids)} runbooks"
    if failed_deletes > 0:
        summary += f" ({failed_deletes} failed)"

    logger.info(f"Bulk delete completed: {summary}")

    return BulkDeleteResponse(
        total_requested=len(request.runbook_ids),
        successful_deletes=successful_deletes,
        failed_deletes=failed_deletes,
        results=results,
        summary=summary
    )


async def _bulk_delete_runbooks_helper(
    runbook_ids: list[str],
    session: AsyncSession
) -> list[BulkDeleteResult]:
    """
    Bulk delete helper that processes deletions within a single transaction.

    Uses savepoints to isolate individual deletion failures without affecting the entire batch.
    Each failed deletion is rolled back to its savepoint while successful deletions are preserved.
    """
    results: list[BulkDeleteResult] = []

    for runbook_id in runbook_ids:
        # Validate ID format first
        try:
            runbook_id_int = int(runbook_id)
        except (ValueError, TypeError):
            logger.warning(f"Invalid runbook ID format: {runbook_id}")
            results.append(BulkDeleteResult(
                runbook_id=runbook_id,
                runbook_title="Unknown",
                status=Status.ERROR,
                error_message=f"Invalid runbook ID format: '{runbook_id}' (must be a valid integer)"
            ))
            continue

        # Use savepoint for transaction isolation
        savepoint = await session.begin_nested()

        try:
            # Fetch runbook
            query = select(RunbookDBModel).where(RunbookDBModel.id == runbook_id_int)
            result = await session.execute(query)
            runbook = result.scalar_one_or_none()

            if not runbook:
                logger.warning(f"Runbook not found for deletion: {runbook_id}")
                results.append(BulkDeleteResult(
                    runbook_id=runbook_id,
                    runbook_title="Unknown",
                    status=Status.ERROR,
                    error_message=f"Runbook with ID '{runbook_id}' not found"
                ))
                await savepoint.rollback()
                continue

            runbook_title = runbook.title

            # Delete runbook (cascade will delete related records)
            await session.delete(runbook)
            await savepoint.commit()

            logger.info(f"Successfully deleted runbook: {runbook_title} (ID: {runbook_id})")
            results.append(BulkDeleteResult(
                runbook_id=runbook_id,
                runbook_title=runbook_title,
                status=Status.SUCCESS
            ))

        except Exception as e:
            # Rollback this specific deletion
            await savepoint.rollback()
            logger.error(f"Failed to delete runbook {runbook_id}: {str(e)}")
            results.append(BulkDeleteResult(
                runbook_id=runbook_id,
                runbook_title="Unknown",
                status=Status.ERROR,
                error_message=str(e)
            ))

    # Commit all successful deletions in one transaction
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to commit bulk delete transaction: {str(e)}")
        # Mark all as failed if commit fails
        for result in results:
            if result.is_success:
                result.status = Status.ERROR
                result.error_message = "Transaction commit failed"

    return results


# Confluence Integration Endpoints

@router.post("/validate-confluence", response_model=ConfluenceValidationResponse)
async def validate_confluence_credentials(
        request: ConfluenceValidationRequest,
        user: str = Depends(get_current_user)
):
    """
    Validate Confluence credentials and connection.

    This endpoint tests the provided Confluence credentials and returns
    information about the authenticated user if successful.
    """
    try:
        logger.info(f"User {user} validating Confluence credentials for {request.base_url}")

        config = {
            'base_url': request.base_url.rstrip('/'),
            'username': request.username,
            'api_token': request.api_token
        }

        result = await ConfluenceService.validate_config(config)

        return ConfluenceValidationResponse(
            status="success",
            user=result['user']
        )

    except HTTPException as e:
        return ConfluenceValidationResponse(
            status="error",
            error=str(e.detail)
        )
    except Exception as e:
        logger.exception(f"Unexpected error validating Confluence credentials")
        return ConfluenceValidationResponse(
            status="error",
            error="An unexpected error occurred during validation"
        )


@router.post("/import-confluence", response_model=ConfluenceImportResponse)
async def import_confluence_runbooks(
        request: ConfluenceImportRequest,
        session: AsyncSession = Depends(get_db_session),
        user: str = Depends(get_current_user)
):
    """
    Import runbooks from Confluence pages.

    Uses Confluence credentials stored in app_config (Setup page).

    Supports:
    - Single page import
    - Recursive child page import
    - Automatic deduplication by Confluence page ID
    - Update existing runbooks if page was already imported
    """
    try:
        logger.info(f"User {user} importing from Confluence: {request.page_url}")

        config = await _get_confluence_config(session)
        client = ConfluenceService.get_confluence_client(config)

        # Fetch parent page
        parent_page = await ConfluenceService.fetch_page_content(
            client,
            request.page_url,
            config['base_url']
        )

        # Store parent page and commit immediately to preserve partial progress
        parent_result = await _store_confluence_page(session, parent_page, user)
        await session.commit()

        child_results = await _fetch_and_import_children(
            session, client, config, request, parent_page, user
        ) if request.include_children else []

        all_results = [parent_result] + child_results
        total_imported = sum(1 for r in all_results if r.status in ['success', 'updated'])
        total_failed = sum(1 for r in all_results if r.status == 'error')

        logger.info(f"Confluence import complete: {total_imported} imported, {total_failed} failed")

        return ConfluenceImportResponse(
            parent_page=parent_result,
            child_pages=child_results,
            total_imported=total_imported,
            total_failed=total_failed
        )

    except HTTPException:
        await session.rollback()
        raise

    except Exception as e:
        await session.rollback()
        logger.exception(f"Failed to import from Confluence")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


async def _fetch_and_import_children(
    session: AsyncSession,
    client,
    config: dict,
    request: ConfluenceImportRequest,
    parent_page: dict,
    user: str
) -> list[ConfluenceImportedPage]:
    """Fetch and import child pages."""
    child_pages = await ConfluenceService.fetch_child_pages(
        client,
        parent_page['page_id'],
        config['base_url'],
        max_depth=request.max_depth,
        max_pages=request.max_pages
    )
    return await _import_child_pages(session, child_pages, parent_page['title'], user)


async def _generate_embedding(content: str, context: str = "content") -> Optional[list[float]]:
    """
    Generate embedding for content with error handling.

    Args:
        content: Text content to embed
        context: Description for logging (e.g., runbook title)

    Returns:
        Embedding vector or None if generation fails
    """
    try:
        embedding_manager = await get_embedding_manager_async()
        embedding_model = embedding_manager.get_embedding_model()
        return await embedding_model.aembed_query(content)
    except Exception as e:
        logger.warning(f"Failed to generate embedding for '{context}': {e}")
        return None


async def _import_single_child_page(
    session: AsyncSession,
    child_page: dict,
    parent_name: str,
    user: str
) -> ConfluenceImportedPage:
    """Import a single child page with error handling."""
    try:
        child_page['title'] = f"{parent_name} - {child_page['title']}"
        result = await _store_confluence_page(session, child_page, user)
        await session.commit()
        return result
    except Exception as e:
        await session.rollback()
        error_msg = str(e)
        logger.error(f"Failed to import child page {child_page.get('page_id', 'unknown')}: {error_msg}")
        return _create_error_import_result(child_page, error_msg)


async def _import_child_pages(
    session: AsyncSession,
    child_pages: list[dict],
    parent_name: str,
    user: str
) -> list[ConfluenceImportedPage]:
    """
    Import child pages with individual error handling and commits.

    Args:
        session: Database session
        child_pages: List of child page data
        parent_name: Parent page title to prefix children
        user: User performing the import

    Returns:
        List of import results
    """
    results = []
    for child_page in child_pages:
        result = await _import_single_child_page(session, child_page, parent_name, user)
        results.append(result)
    return results


def _create_error_import_result(page_data: dict, error_message: str = None) -> ConfluenceImportedPage:
    """
    Create an error result for a failed Confluence page import.

    Args:
        page_data: Dictionary with page metadata
        error_message: Optional error message describing what went wrong

    Returns:
        ConfluenceImportedPage with status='error' and error message
    """
    return ConfluenceImportedPage(
        title=page_data.get('title', 'Unknown'),
        runbook_id='',
        page_id=page_data.get('page_id', ''),
        url=page_data.get('url', ''),
        status='error',
        error=error_message or 'Import failed'
    )


def _build_confluence_source_metadata(page_data: dict) -> dict:
    """Build source metadata dict for Confluence pages."""
    return {
        'page_id': page_data['page_id'],
        'page_url': page_data['url'],
        'version': page_data['version']
    }


def _build_upsert_statement(
    page_data: dict,
    embedding: Optional[list[float]],
    current_time: dt
) -> any:
    """Build PostgreSQL upsert statement for Confluence page."""
    content_size = len(page_data['content'].encode('utf-8'))
    source_metadata = _build_confluence_source_metadata(page_data)

    return insert(RunbookDBModel).values(
        title=page_data['title'],
        content=page_data['content'],
        content_size_bytes=content_size,
        source_type='confluence',
        source_metadata=source_metadata,
        embedding=embedding,
        created_at=current_time,
        updated_at=current_time
    ).on_conflict_do_update(
        index_elements=[text("(source_metadata->>'page_id')")],
        index_where=text("source_type = 'confluence' AND source_metadata->>'page_id' IS NOT NULL"),
        set_={
            'title': page_data['title'],
            'content': page_data['content'],
            'content_size_bytes': content_size,
            'source_metadata': source_metadata,
            # Use NOW() for updated_at so it always differs from created_at on updates
            # This prevents the race condition where both timestamps are equal
            'updated_at': text("NOW()"),
            'embedding': embedding
        }
    ).returning(RunbookDBModel.id, text("xmax::text::int"))


def _create_import_result(
    page_data: dict,
    runbook_id: str,
    was_created: bool,
    embedding_status: str = 'success'
) -> ConfluenceImportedPage:
    """Create successful import result with embedding status."""
    status = 'success' if was_created else 'updated'
    action = 'Created' if was_created else 'Updated'
    logger.info(f"{action} runbook for Confluence page {page_data['page_id']}")

    return ConfluenceImportedPage(
        title=page_data['title'],
        runbook_id=runbook_id,
        page_id=page_data['page_id'],
        url=page_data['url'],
        status=status,
        embedding_status=embedding_status
    )


async def _store_confluence_page(
        session: AsyncSession,
        page_data: dict,
        user: str
) -> ConfluenceImportedPage:
    """
    Store or update a Confluence page as a runbook using atomic upsert.

    Uses PostgreSQL's INSERT...ON CONFLICT to handle race conditions atomically.

    Returns:
        ConfluenceImportedPage with import status and embedding status
    """
    embedding_status = 'success'
    try:
        try:
            embedding = await _generate_embedding(page_data['content'], page_data['title'])
        except Exception as embed_error:
            logger.warning(f"Failed to generate embedding for page {page_data.get('page_id')}: {embed_error}")
            embedding = None
            embedding_status = f"failed: {str(embed_error)}"

        current_time = dt.now(timezone.utc)
        stmt = _build_upsert_statement(page_data, embedding, current_time)

        result = await session.execute(stmt)
        row = result.fetchone()
        runbook_id = str(row[0])
        # xmax = 0 means INSERT, xmax > 0 means UPDATE
        # This works because the INSERT uses real DB session (not mocked in tests)
        was_created = (row[1] == 0)
        await session.flush()

        return _create_import_result(page_data, runbook_id, was_created, embedding_status)
    except Exception as e:
        logger.exception(f"Failed to store Confluence page {page_data.get('page_id')}")
        return _create_error_import_result(page_data, str(e))


@router.post("/sync-confluence")
async def sync_confluence_runbooks(
        user: str = Depends(get_current_user)
):
    """
    Manually trigger a Confluence sync job to update all Confluence runbooks.

    This endpoint enqueues a background job that will sync all runbooks
    imported from Confluence with their source pages.
    """
    try:
        logger.info(f"User {user} manually triggered Confluence sync")
        job_id = enqueue_confluence_sync_now()

        return {
            "status": "success",
            "job_id": job_id,
            "message": "Confluence sync job enqueued successfully"
        }

    except Exception as e:
        logger.exception("Failed to enqueue Confluence sync job")
        raise HTTPException(status_code=500, detail=f"Failed to trigger sync: {str(e)}")
