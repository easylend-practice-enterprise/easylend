from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    """
    Payload structuur van de JWT token (wat er ín de token gesigned en base64url-gecodeerd zit).
    Dit gebruiken we intern in de applicatie om permissies te checken.
    """

    sub: UUID = Field(..., description="Subject: De unieke user_id van de gebruiker")
    role: str = Field(
        ..., description="De rol van de gebruiker (bijv. Admin, User, Kiosk)"
    )
    exp: datetime = Field(
        ..., description="Expiration: De verloopdatum en tijd van de token"
    )
    jti: UUID = Field(
        ...,
        description="JWT ID: Unieke identifier voor deze specifieke token (voor revocation)",
    )


class Token(BaseModel):
    """
    Response model dat naar de client (app/frontend/kiosk) wordt gestuurd
    na een succesvolle login.
    """

    access_token: str = Field(
        ..., description="De JWT access token (geldig voor bijv. 15 min)"
    )
    refresh_token: str = Field(
        ...,
        description="De string om een nieuwe access token aan te vragen (geldig voor bijv. 7 dagen)",
    )
    token_type: str = Field(
        default="Bearer", description="Het type token (standaard 'Bearer')"
    )
