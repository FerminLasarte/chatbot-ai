"""marcar las conversaciones derivadas a una persona

Revision ID: e5a72d1b8c94
Revises: d81c3f5a9e27
Create Date: 2026-08-31 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a72d1b8c94'
down_revision: Union[str, Sequence[str], None] = 'd81c3f5a9e27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NULL = no se derivo. Las conversaciones que ya existen quedan asi, que es
    # la verdad: hasta ahora el asistente no tenia forma de derivar nada.
    op.add_column(
        'conversations', sa.Column('derivada_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'derivada_at')
