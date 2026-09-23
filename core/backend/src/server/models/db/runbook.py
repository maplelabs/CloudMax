"""
Database models for Runbook storage.
Defines the schema for PostgreSQL tables using SQLAlchemy.
"""
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, String, Text, Index, Enum, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column

from .base import Base, TimestampMixin


class Runbook(TimestampMixin, Base):
    """
    SQLAlchemy model for runbooks table.

    Supports multiple source types with flexible metadata storage.

    source_metadata examples:

    For Confluence:
    {
        "page_id": "12345",
        "page_url": "http://confluence.example.com/wiki/pages/12345",
        "version": 7,
        "space_key": "SRE",
        "parent_page_id": null
    }
    Note: Use updated_at column for last sync time

    For file uploads:
    {
        "filename": "sre_runbook.md",
        "original_path": "/uploads/runbooks/sre_runbook.md"
    }
    Note: Use created_at column for upload time

    For future sources (GitHub, Google Docs, etc.):
    {
        "repo": "org/repo",
        "path": "docs/runbooks/incident.md",
        "commit_sha": "abc123...",
        "branch": "main"
    }
    """
    __tablename__ = "runbooks"

    # Table arguments to include indexes as part of table definition
    __table_args__ = (
        # Vector index for semantic search - created automatically with table
        # TODO: Do we need this index. This would be helpful when we have millions of entries. For our purpose,
        #  we can probably get away with just normal brute force search which doesnt need index.
        Index(
            'idx_runbooks_embedding_hnsw',
            'embedding',
            postgresql_using='hnsw',
            postgresql_with={'m': 16, 'ef_construction': 64},
            postgresql_ops={'embedding': 'vector_l2_ops'}
        ),
        # Index for source type filtering
        Index('idx_runbooks_source_type', 'source_type'),
        # GIN index for JSONB queries on source_metadata
        Index('idx_runbooks_source_metadata_gin', 'source_metadata', postgresql_using='gin'),
        # Unique index for Confluence page_id (prevents duplicate imports from same page)
        Index(
            'idx_runbooks_confluence_page_id_unique',
            text("((source_metadata->>'page_id'))"),
            unique=True,
            postgresql_where=text("source_type = 'confluence' AND source_metadata->>'page_id' IS NOT NULL")
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    content_size_bytes = Column(Integer, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True)

    # Source tracking
    source_type = Column(
        Enum('file', 'confluence', 'github', 'google_docs', name='runbook_source_type'),
        nullable=False,
        server_default='file',
        doc="Source of the runbook content (file, confluence, github, google_docs, etc.)"
    )

    source_metadata = Column(
        JSONB,
        nullable=True,
        server_default='{}',
        doc="""
        Flexible metadata storage for different source types.
        For Confluence: {page_id, page_url, version, space_key, parent_page_id}
        For file: {filename, original_path}
        For future sources: custom fields as needed
        Note: Use updated_at for last sync/modification time instead of storing in metadata
        """
    )
