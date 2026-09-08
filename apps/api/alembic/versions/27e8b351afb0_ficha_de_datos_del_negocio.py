"""ficha de datos del negocio

Revision ID: 27e8b351afb0
Revises: e5a72d1b8c94
Create Date: 2026-09-07 23:22:31.985162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '27e8b351afb0'
down_revision: Union[str, Sequence[str], None] = 'e5a72d1b8c94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOT NULL con server_default '{}': los clientes que ya existen quedan con
    # una ficha vacia, que es la verdad -no cargaron nada- y ademas evita el
    # tercer estado. Con la columna nullable habria que distinguir en todo el
    # codigo entre "sin ficha" y "ficha vacia", que para el prompt son lo mismo.
    #
    # El server_default se queda en la tabla a proposito: es lo que hace que un
    # INSERT hecho desde psql -o desde un test que no pasa por el modelo- no
    # pueda dejar la columna en NULL.
    op.add_column('tenants', sa.Column('business_profile', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenants', 'business_profile')
