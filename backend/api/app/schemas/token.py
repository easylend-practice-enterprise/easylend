from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    """
    Payload structure of the JWT token (the data that is signed and base64url-encoded inside the token).
    Used internally by the application to verify permissions.
    """

    sub: UUID = Field(..., description="Subject: The unique user_id of the user")
    role: str = Field(..., description="Role of the user (e.g. Admin, User, Kiosk)")
    exp: datetime = Field(
        ..., description="Expiration: The expiry date and time of the token"
    )
    jti: UUID = Field(
        ...,
        description="JWT ID: Unique identifier for this specific token (used for revocation)",
    )


class Token(BaseModel):
    """
    Response model sent to the client (app/frontend/kiosk) after a successful login.
    """

    access_token: str = Field(
        ..., description="The JWT access token (valid for e.g. 15 minutes)"
    )
    refresh_token: str = Field(
        ...,
        description="The string used to request a new access token (valid for e.g. 7 days)",
    )
    token_type: str = Field(
        default="Bearer", description="Token type (standard 'Bearer')"
    )
