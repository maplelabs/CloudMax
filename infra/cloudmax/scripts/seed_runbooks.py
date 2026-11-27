"""
One-off seed: populate CloudMax's runbooks table with sample Markdown
runbooks from infra/cloudmax/seed-runbooks/ so the Runbooks page isn't
empty immediately after a demo deploy.

Run inside the cloudmax-backend container (has DATABASE_URL + all the
app's own models already available on PYTHONPATH=/app), so this reuses the
exact same SQLAlchemy models / embedding manager the running app itself
uses -- same code path as a real file upload (see
apis_v1/runbooks.py::_process_single_file_core), just driven directly
against the DB instead of via the HTTP API.

Idempotent: skips any file whose title (filename without extension)
already exists as a runbook -- safe to re-run on an already-seeded /
snapshot-restored VM (matches the dedup-by-title behavior the real
upload endpoint already enforces).

The seed directory (SEED_RUNBOOKS_DIR, default
infra/cloudmax/seed-runbooks/ relative to the repo root mounted into this
container) only needs to contain .md/.txt files -- same restriction the
upload endpoint enforces (SUPPORTED_FILE_EXTENSIONS).

Embedding generation is best-effort: if it fails (e.g. embedding config
not seeded yet, or a transient API error), the runbook is still stored
without an embedding -- it just won't be reachable via semantic search
until re-generated, same soft-fail behavior as _generate_embedding() in
the Confluence import path.
"""
import asyncio
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db import RunbookDBModel
from src.server.utilities.embedding_manager import get_embedding_manager_async

SUPPORTED_EXTENSIONS = ('.md', '.txt')
SEED_RUNBOOKS_DIR = Path(os.environ.get('SEED_RUNBOOKS_DIR', '/tmp/seed-runbooks'))


def _title_from_filename(filename: str) -> str:
    """Same rule the real upload endpoint uses: filename minus extension."""
    title = filename.rsplit('.', 1)[0]
    return title.strip() if title else "Untitled Runbook"


async def _generate_embedding(content: str, context: str):
    try:
        embedding_manager = await get_embedding_manager_async()
        embedding_model = embedding_manager.get_embedding_model()
        return await embedding_model.aembed_query(content)
    except Exception as e:
        print(f"::warning::Failed to generate embedding for '{context}': {e} -- storing without embedding.")
        return None


async def main():
    if not SEED_RUNBOOKS_DIR.is_dir():
        raise SystemExit(f"Seed runbooks directory not found: {SEED_RUNBOOKS_DIR}")

    seed_files = sorted(
        p for p in SEED_RUNBOOKS_DIR.iterdir()
        if p.is_file() and p.name.endswith(SUPPORTED_EXTENSIONS)
    )
    if not seed_files:
        print(f"No {SUPPORTED_EXTENSIONS} files found in {SEED_RUNBOOKS_DIR} -- nothing to seed.")
        return

    created, skipped, failed = 0, 0, 0

    async with async_db_session() as session:
        for path in seed_files:
            title = _title_from_filename(path.name)

            existing = await session.execute(
                select(RunbookDBModel).where(RunbookDBModel.title == title)
            )
            if existing.scalars().first():
                print(f"Skipping '{title}' -- runbook with this title already exists.")
                skipped += 1
                continue

            content = path.read_text(encoding='utf-8').strip()
            if not content:
                print(f"::warning::Skipping '{path.name}' -- file is empty.")
                skipped += 1
                continue

            embedding = await _generate_embedding(content, title)

            try:
                runbook = RunbookDBModel(
                    title=title,
                    content=content,
                    content_size_bytes=len(content.encode('utf-8')),
                    source_type='file',
                    source_metadata={'filename': path.name, 'seeded': True},
                    embedding=embedding,
                )
                session.add(runbook)
                await session.commit()
                print(f"Seeded runbook '{title}' (id={runbook.id}).")
                created += 1
            except IntegrityError as e:
                await session.rollback()
                print(f"::warning::Failed to seed '{title}': {e}")
                failed += 1

    print(f"Done. Created={created} Skipped={skipped} Failed={failed}")


asyncio.run(main())
