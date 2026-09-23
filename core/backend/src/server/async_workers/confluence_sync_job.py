"""
Confluence Sync Job for automatically syncing Confluence runbooks.

This job runs daily and syncs all runbooks that were imported from Confluence.
It checks the Confluence page version and only fetches full content if the version changed.
"""
import asyncio
import logging
import time
from datetime import datetime as dt, timezone
from typing import Optional

from rq import get_current_job
from sqlalchemy import select

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db import AppConfigDBModel, RunbookDBModel
from src.server.services.confluence import ConfluenceService
from src.server.utilities import get_queue, get_scheduler
from src.server.utilities.embedding_manager import get_embedding_manager_async

logger = logging.getLogger(__name__)

# Constants
COMMIT_BATCH_SIZE = 10
SYNC_CRON_SCHEDULE = "0 2 * * *"  # 2 AM daily
SYNC_JOB_TIMEOUT = "1h"


def _is_confluence_configured(app_config: Optional[AppConfigDBModel]) -> bool:
    """Check if app config has valid Confluence configuration."""
    if not app_config or not app_config.external_runbook_config:
        return False

    confluence_config = app_config.external_runbook_config.get('confluence')
    return confluence_config and confluence_config.get('enabled')


def _extract_confluence_credentials(confluence_config: dict) -> Optional[dict]:
    """Extract and validate Confluence credentials from config."""
    config = {
        'base_url': confluence_config.get('base_url', '').rstrip('/'),
        'username': confluence_config.get('username'),
        'api_token': confluence_config.get('api_token')
    }

    return config if all(config.values()) else None


async def _get_confluence_config_for_sync() -> Optional[dict]:
    """
    Retrieve and validate Confluence configuration for sync.

    Returns:
        Configuration dict or None if not configured
    """
    async with async_db_session() as session:
        result = await session.execute(select(AppConfigDBModel).limit(1))
        app_config = result.scalar_one_or_none()

        if not _is_confluence_configured(app_config):
            logger.info("Confluence integration not configured or enabled")
            return None

        confluence_config = app_config.external_runbook_config['confluence']
        config = _extract_confluence_credentials(confluence_config)

        if not config:
            logger.warning("Incomplete Confluence configuration")
            return None

        return config


async def _get_page_version(client, page_id: str) -> Optional[int]:
    """Fetch current version of a Confluence page."""
    from src.server.services.confluence.client import _run_in_executor

    try:
        page_metadata = await _run_in_executor(
            client.get_page_by_id,
            page_id,
            expand='version'
        )
        return page_metadata['version']['number']
    except Exception as e:
        logger.error(f"Failed to fetch version for page {page_id}: {e}")
        return None


def _normalize_embedding(raw_embedding) -> list[float]:
    """Normalize embedding to ensure consistent format."""
    if isinstance(raw_embedding, str):
        return [float(x.strip()) for x in raw_embedding.strip('[]').split(',')]

    if isinstance(raw_embedding, (list, tuple)):
        return list(raw_embedding)

    return raw_embedding.tolist() if hasattr(raw_embedding, 'tolist') else list(raw_embedding)


async def _generate_embedding_for_runbook(content: str, title: str) -> Optional[list[float]]:
    """Generate and normalize embedding for runbook content."""
    try:
        embedding_manager = await get_embedding_manager_async()
        embedding_model = embedding_manager.get_embedding_model()
        raw_embedding = await embedding_model.aembed_query(content)
        return _normalize_embedding(raw_embedding)
    except Exception as e:
        logger.warning(f"Failed to generate embedding for '{title}': {e}")
        return None


async def _update_runbook_content(runbook: RunbookDBModel, page_data: dict) -> None:
    """Update runbook with new content and metadata."""
    current_time = dt.now(timezone.utc)

    runbook.title = page_data['title']
    runbook.content = page_data['content']
    runbook.content_size_bytes = len(page_data['content'].encode('utf-8'))
    runbook.source_metadata = {
        **runbook.source_metadata,
        'version': page_data['version'],
        'page_url': page_data['url']
    }
    runbook.updated_at = current_time

    embedding = await _generate_embedding_for_runbook(page_data['content'], runbook.title)
    if embedding:
        runbook.embedding = embedding


def _should_update_runbook(runbook: RunbookDBModel, current_version: int) -> bool:
    """Check if runbook needs updating based on version."""
    stored_version = runbook.source_metadata.get('version')

    if stored_version == current_version:
        logger.debug(f"Runbook '{runbook.title}' is up-to-date (version {current_version})")
        return False

    logger.info(
        f"Updating runbook '{runbook.title}' "
        f"from version {stored_version} to {current_version}"
    )
    return True


async def _update_runbook_from_confluence(
    runbook: RunbookDBModel,
    client,
    config: dict
) -> bool:
    """
    Update a single runbook from its Confluence source.

    Returns:
        True if updated, False if unchanged or failed
    """
    try:
        page_id = runbook.source_metadata.get('page_id')
        if not page_id:
            logger.warning(f"Runbook '{runbook.title}' missing page_id in source_metadata")
            return False

        current_version = await _get_page_version(client, page_id)
        if not current_version:
            return False

        if not _should_update_runbook(runbook, current_version):
            return False

        page_url = runbook.source_metadata.get('page_url') or f"{config['base_url']}/wiki/pages/{page_id}"
        page_data = await ConfluenceService.fetch_page_content(client, page_url, config['base_url'])
        await _update_runbook_content(runbook, page_data)
        return True
    except Exception as e:
        page_id = runbook.source_metadata.get('page_id', 'unknown')
        logger.error(f"Failed to sync runbook '{runbook.title}' (page_id: {page_id}): {e}")
        return False


def _init_sync_stats() -> dict:
    """Initialize sync statistics dict."""
    return {
        "checked": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
        "skipped_no_config": 0
    }


def _update_stats(stats: dict, was_updated: bool) -> None:
    """Update statistics based on sync result."""
    if was_updated is True:
        stats["updated"] += 1
    elif was_updated is False:
        stats["unchanged"] += 1
    else:
        stats["errors"] += 1


def _should_commit_batch(stats: dict) -> bool:
    """Check if we should commit current batch."""
    return stats["updated"] > 0 and stats["updated"] % COMMIT_BATCH_SIZE == 0


async def _sync_runbook_batch(
    session,
    runbooks: list[RunbookDBModel],
    client,
    config: dict,
    stats: dict
) -> None:
    """Sync a batch of runbooks and update statistics."""
    for runbook in runbooks:
        stats["checked"] += 1
        was_updated = await _update_runbook_from_confluence(runbook, client, config)
        _update_stats(stats, was_updated)

        if _should_commit_batch(stats):
            await session.commit()
            logger.info(
                f"Progress: {stats['updated']} updated, "
                f"{stats['unchanged']} unchanged, {stats['errors']} errors"
            )


async def sync_confluence_runbooks() -> dict:
    """
    Sync all Confluence runbooks with their source pages.

    This function:
    1. Retrieves Confluence credentials from app config
    2. Finds all runbooks imported from Confluence
    3. Checks each page version on Confluence
    4. Updates runbooks if version changed
    5. Generates new embeddings for updated content

    Returns:
        Dictionary with sync statistics
    """
    stats = _init_sync_stats()
    logger.info("Starting Confluence runbook sync")

    try:
        config = await _get_confluence_config_for_sync()
        if not config:
            stats["skipped_no_config"] = 1
            return stats

        client = ConfluenceService.get_confluence_client(config)

        async with async_db_session() as session:
            result = await session.execute(
                select(RunbookDBModel)
                .where(RunbookDBModel.source_type == 'confluence')
                .where(RunbookDBModel.source_metadata['page_id'].astext.isnot(None))
            )
            confluence_runbooks = result.scalars().all()
            logger.info(f"Found {len(confluence_runbooks)} Confluence runbooks to sync")

            await _sync_runbook_batch(session, confluence_runbooks, client, config, stats)
            await session.commit()

        logger.info(f"Confluence sync completed: {stats}")

    except Exception:
        logger.exception("Error during Confluence sync")

    return stats



def execute_confluence_sync_job():
    """
    Execute Confluence sync job.

    This is the RQ job entry point that runs the async sync function.
    """
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.info(f"Starting Confluence sync job {job_id}")
    start_time = time.time()

    try:
        stats = asyncio.run(sync_confluence_runbooks())
        processing_time = time.time() - start_time
        logger.info(f"Completed Confluence sync job {job_id} in {processing_time:.2f}s: {stats}")
        return stats
    except Exception:
        processing_time = time.time() - start_time
        logger.exception(f"Failed to execute Confluence sync job {job_id}")
        logger.error(f"Confluence sync job {job_id} failed after {processing_time:.2f}s")
        raise


def _remove_existing_sync_jobs(scheduler) -> None:
    """Remove any existing Confluence sync jobs to avoid duplicates."""
    job_func_name = 'src.server.async_workers.confluence_sync_job.execute_confluence_sync_job'
    for job in scheduler.get_jobs():
        if job.func_name == job_func_name:
            logger.info(f"Removing existing Confluence sync job: {job.id}")
            scheduler.cancel(job)


def schedule_daily_confluence_sync():
    """
    Schedule daily Confluence sync job.

    This should be called once during application startup to register
    the recurring job with RQ Scheduler.
    """
    try:
        scheduler = get_scheduler("default")
        _remove_existing_sync_jobs(scheduler)

        job = scheduler.cron(
            SYNC_CRON_SCHEDULE,
            func=execute_confluence_sync_job,
            timeout=SYNC_JOB_TIMEOUT,
            queue_name="default",
            id="confluence_daily_sync"
        )

        logger.info(f"Scheduled daily Confluence sync job: {job.id}")
        return job.id

    except Exception:
        logger.exception("Failed to schedule daily Confluence sync job")
        raise


def enqueue_confluence_sync_now() -> str:
    """
    Manually trigger a Confluence sync job immediately.

    Returns:
        Job ID of the enqueued sync job
    """
    queue = get_queue("default")

    job = queue.enqueue(
        execute_confluence_sync_job,
        job_timeout=SYNC_JOB_TIMEOUT
    )

    logger.info(f"Enqueued immediate Confluence sync job: {job.id}")
    return job.id
