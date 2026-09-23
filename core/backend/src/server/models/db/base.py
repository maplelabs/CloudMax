from sqlalchemy import TIMESTAMP, Column, text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TimestampMixin:
    """Reusable timestamp mixin for created_at and updated_at columns."""
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
