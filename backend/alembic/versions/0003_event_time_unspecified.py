import sqlalchemy as sa
from alembic import op

revision="0003_event_time_unspecified"
down_revision="0002_activity_sheet"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("events",sa.Column("time_unspecified",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.alter_column("events","time_unspecified",server_default=None)

def downgrade():
    op.drop_column("events","time_unspecified")
