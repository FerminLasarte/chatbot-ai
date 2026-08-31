"""autor de cada mensaje: el bot o una persona

Revision ID: d81c3f5a9e27
Revises: b7e41c9a2d38
Create Date: 2026-08-31 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd81c3f5a9e27'
down_revision: Union[str, Sequence[str], None] = 'b7e41c9a2d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Sin backfill a proposito. Los mensajes que ya estaban se escribieron
    # cuando nadie anotaba el autor, y ponerles "bot" seria adivinar justo en el
    # caso que importa: las conversaciones donde el comercio contesto a mano.
    # NULL dice la verdad -no se sabe- y la vista lo muestra sin atribuir.
    op.add_column('messages', sa.Column('autor', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'autor')
