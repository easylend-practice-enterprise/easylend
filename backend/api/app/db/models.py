import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Enum, Float
from sqlalchemy.dialects.postgresql import JSONB


class Base(DeclarativeBase):
    pass


# ROLES
class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    users: Mapped[list["User"]] = relationship("User", back_populates="role")


# USERS
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.role_id"), nullable=False
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    nfc_tag_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ban_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped["Role"] = relationship("Role", back_populates="users")


# ENUMS
class KioskStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"


class LockerStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"
    ERROR_OPEN = "ERROR_OPEN"


class AssetStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BORROWED = "BORROWED"
    RESERVED = "RESERVED"
    MAINTENANCE = "MAINTENANCE"
    LOST = "LOST"


class LoanStatus(str, enum.Enum):
    RESERVED = "RESERVED"
    ACTIVE = "ACTIVE"
    OVERDUE = "OVERDUE"
    COMPLETED = "COMPLETED"
    FRAUD_SUSPECTED = "FRAUD_SUSPECTED"
    DISPUTED = "DISPUTED"
    PENDING_INSPECTION = "PENDING_INSPECTION"


class EvaluationType(str, enum.Enum):
    CHECKOUT = "CHECKOUT"
    RETURN = "RETURN"


# FYSIEKE INFTRASTRUCTUUR: KIOSKS & LOCKERS
class Kiosk(Base):
    __tablename__ = "kiosks"

    kiosk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_description: Mapped[str] = mapped_column(String(255), nullable=False)
    kiosk_status: Mapped[KioskStatus] = mapped_column(
        Enum(KioskStatus), default=KioskStatus.ONLINE
    )

    lockers: Mapped[list["Locker"]] = relationship("Locker", back_populates="kiosk")


class Locker(Base):
    __tablename__ = "lockers"

    locker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kiosk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kiosks.kiosk_id"), nullable=False
    )

    logical_number: Mapped[int] = mapped_column(Integer, nullable=False)
    locker_status: Mapped[LockerStatus] = mapped_column(
        Enum(LockerStatus), default=LockerStatus.AVAILABLE
    )

    kiosk: Mapped["Kiosk"] = relationship("Kiosk", back_populates="lockers")
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="locker")


# CATEGORIEËN
class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="category")


# ASSETS
class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.category_id"), nullable=False
    )

    locker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lockers.locker_id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aztec_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    asset_status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus), default=AssetStatus.AVAILABLE
    )

    category: Mapped["Category"] = relationship("Category", back_populates="assets")
    locker: Mapped["Locker"] = relationship("Locker", back_populates="assets")


# LOANS (TRANSACTIES)
class Loan(Base):
    __tablename__ = "loans"

    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.asset_id"), nullable=False
    )
    checkout_locker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lockers.locker_id"), nullable=False
    )

    return_locker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lockers.locker_id"), nullable=True
    )

    reserved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    borrowed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    returned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    loan_status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus), default=LoanStatus.RESERVED
    )

    user: Mapped["User"] = relationship("User", backref="loans")
    asset: Mapped["Asset"] = relationship("Asset", backref="loans")
    checkout_locker: Mapped["Locker"] = relationship(
        "Locker", foreign_keys=[checkout_locker_id]
    )
    return_locker: Mapped["Locker"] = relationship(
        "Locker", foreign_keys=[return_locker_id]
    )
    evaluations: Mapped[list["AIEvaluation"]] = relationship(
        "AIEvaluation", back_populates="loan"
    )


# AI EVALUATIES
class AIEvaluation(Base):
    __tablename__ = "ai_evaluations"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    loan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loans.loan_id"), nullable=False
    )

    evaluation_type: Mapped[EvaluationType] = mapped_column(
        Enum(EvaluationType), nullable=False
    )
    photo_url: Mapped[str] = mapped_column(String(255), nullable=False)
    ai_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    detected_objects: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Performance denormalisatie voor snelle queries zonder joins
    has_damage_detected: Mapped[bool] = mapped_column(Boolean, default=False)

    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    loan: Mapped["Loan"] = relationship("Loan", back_populates="evaluations")
    damage_reports: Mapped[list["DamageReport"]] = relationship(
        "DamageReport", back_populates="evaluation"
    )


# SCHADERAPPORTEN
class DamageReport(Base):
    __tablename__ = "damage_reports"

    damage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_evaluations.evaluation_id"), nullable=False
    )

    damage_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)

    # YOLOv26 bounding boxes / segmentations data
    segmentation_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requires_repair: Mapped[bool] = mapped_column(Boolean, default=False)

    evaluation: Mapped["AIEvaluation"] = relationship(
        "AIEvaluation", back_populates="damage_reports"
    )


# SECURITY & AUDIT LOGS
class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )

    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", backref="audit_logs")
