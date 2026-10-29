from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import AuditLog, User

def audit(db: Session, actor: User | None, action: str, entity_type: str, entity_id=None, before=None, after=None):
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, entity_type=entity_type, entity_id=entity_id, before_data=before, after_data=after, created_at=datetime.now(timezone.utc)))
