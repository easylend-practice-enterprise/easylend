from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import EvaluationType, LoanStatus


class QuarantineLoanView(BaseModel):
    """Quarantined loan with joined relation names for the admin dashboard."""

    model_config = ConfigDict(from_attributes=True)

    loan_id: UUID
    asset_name: str
    user_name: str
    kiosk_name: str
    reserved_at: datetime | None
    borrowed_at: datetime | None
    returned_at: datetime | None
    loan_status: LoanStatus


class EvaluationDetailView(BaseModel):
    """Most recent AI evaluation for a loan, returned to the admin for judging."""

    model_config = ConfigDict(from_attributes=True)

    evaluation_id: UUID
    evaluation_type: EvaluationType
    photo_url: str
    ai_confidence: float
    has_damage_detected: bool
    detected_objects: dict | None
    model_version: str
    analyzed_at: datetime


class QuarantineJudgmentRequest(BaseModel):
    """Admin verdict on a quarantined AI evaluation."""

    is_approved: bool
    rejection_reason: str | None = Field(
        None, description="Required when is_approved is False"
    )
