import sqlalchemy as sa
from alembic import op

revision="0003_event_time_unspecified"
down_revision="0002_activity_sheet"
branch_labels=None
depends_on=None

def upgrade():
    # The initial migration uses the live SQLAlchemy metadata to create tables.
    # On a fresh database that metadata can already include this later column,
    # while an existing database may still need it. Inspect the real schema so
    # both cases can safely advance to this revision.
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("events")}
    if "time_unspecified" not in columns:
        op.add_column(
            "events",
            sa.Column(
                "time_unspecified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.alter_column("events", "time_unspecified", server_default=None)

def downgrade():
    op.drop_column("events","time_unspecified")
