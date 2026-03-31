from datetime import datetime
from uuid import UUID

from pydantic import AliasPath, BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., max_length=255)
    nfc_tag_id: str | None = Field(default=None, max_length=100)


class UserCreate(UserBase):
    role_id: UUID
    pin: str = Field(..., min_length=4, max_length=32)
    accepted_privacy_policy: bool = Field(default=False)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=255)
    nfc_tag_id: str | None = Field(default=None, max_length=100)
    role_id: UUID | None = None
    pin: str | None = Field(default=None, min_length=4, max_length=32)
    failed_login_attempts: int | None = Field(default=None, ge=0)
    locked_until: datetime | None = None
    is_active: bool | None = None
    ban_reason: str | None = Field(default=None, max_length=255)
    accepted_privacy_policy: bool | None = None

    @field_validator("accepted_privacy_policy", mode="before")
    @classmethod
    def reject_explicit_none(cls, v):
        if v is None:
            raise ValueError("accepted_privacy_policy cannot be explicitly null")
        return v


class UserNfcUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nfc_tag_id: str = Field(..., min_length=1, max_length=100)


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: UUID
    role_name: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    role_id: UUID
    role_name: str = Field(validation_alias=AliasPath("role", "role_name"))
    first_name: str
    last_name: str
    email: str
    nfc_tag_id: str | None
    failed_login_attempts: int
    locked_until: datetime | None
    is_active: bool
    ban_reason: str | None
    is_anonymized: bool
    accepted_privacy_policy: bool


class UserListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UserResponse]
    total: int
