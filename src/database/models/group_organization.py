"""Group-Organization Link ORM Model"""

import uuid

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class GroupOrganization(Base):
    __tablename__ = "group_organizations"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_root: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    group = relationship("DocumentGroup", back_populates="organization_links")
    organization = relationship("Organization", back_populates="group_links")

    def __repr__(self) -> str:
        return f"<GroupOrganization group={self.group_id} org={self.org_id}>"
