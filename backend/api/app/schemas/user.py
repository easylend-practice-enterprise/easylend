from datetime import datetime
from uuid import UUID

from pydantic import AliasPath, BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., max_length=255)
    nfc_tag_id: str | None = Field(default=None, max_length=100)


class UserCreate(UserBase):
    role_id: UUID
    pin: str = Field(..., min_length=4, max_length=32)


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


class UserListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UserResponse]
    total: int
