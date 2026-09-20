"""RanahResearch domain package: SQLAlchemy models, schemas, and repositories.

PostgreSQL is the source of truth. Import ranah_domain.models to register all
tables on Base.metadata (needed by Alembic autogenerate and create_all).
"""

from ranah_domain.db import Base

__all__ = ["Base"]
