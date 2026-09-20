import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ranah_domain.db import Base
from ranah_domain.enums import ProjectMemberRole
from ranah_domain.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(50), default="free")
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    auth_provider: Mapped[str] = mapped_column(String(50))
    provider_subject: Mapped[str] = mapped_column(String(200))

    organization: Mapped[Organization] = relationship(back_populates="users")

    __table_args__ = (UniqueConstraint("auth_provider", "provider_subject"),)


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ProjectMemberRole] = mapped_column(enum_column(ProjectMemberRole, length=20))
