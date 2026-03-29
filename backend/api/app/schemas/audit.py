from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: UUID
    user_id: UUID | None
    action_type: str
    payload: dict | None
    previous_hash: str
    current_hash: str
    created_at: datetime


class AuditVerifyResponse(BaseModel):
    is_valid: bool
    tampered_record_id: UUID | None
