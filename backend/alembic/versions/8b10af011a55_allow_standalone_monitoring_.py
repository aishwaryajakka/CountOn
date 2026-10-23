"""allow standalone monitoring notifications

Revision ID: 8b10af011a55
Revises: 5d201f68ac90
Create Date: 2026-10-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b10af011a55"
down_revision: Union[str, Sequence[str], None] = "5d201f68ac90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "notifications",
        "evaluation_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "notifications",
        "evaluation_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
