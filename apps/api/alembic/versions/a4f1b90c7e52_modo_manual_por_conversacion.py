"""modo manual por conversacion

Revision ID: a4f1b90c7e52
Revises: c2533a810321
Create Date: 2026-08-12 10:12:04.331207

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f1b90c7e52'
down_revision: Union[str, Sequence[str], None] = 'c2533a810321'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'conversations',
        sa.Column('pausada_hasta', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'pausada_hasta')
