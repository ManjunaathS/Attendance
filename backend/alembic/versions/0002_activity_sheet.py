from alembic import op
from app.models import ActivitySheet

revision="0002_activity_sheet"
down_revision="0001_initial"
branch_labels=None
depends_on=None

def upgrade():
    ActivitySheet.__table__.create(bind=op.get_bind(),checkfirst=True)

def downgrade():
    ActivitySheet.__table__.drop(bind=op.get_bind(),checkfirst=True)
