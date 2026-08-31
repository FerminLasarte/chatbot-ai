"""guardar el waba_id del cliente

Revision ID: b7e41c9a2d38
Revises: a4f1b90c7e52
Create Date: 2026-08-31 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e41c9a2d38'
down_revision: Union[str, Sequence[str], None] = 'a4f1b90c7e52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable a proposito y sin backfill posible: los clientes dados de alta
    # antes de esta migracion se conectaron sin que nadie guardara el waba_id, y
    # no hay de donde sacarlo sin volver a pedirselo a Meta.
    op.add_column('tenants', sa.Column('whatsapp_waba_id', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenants', 'whatsapp_waba_id')
