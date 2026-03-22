from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.database import get_db
from app.db.models import Role, User
from app.schemas.user import RoleResponse

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
    },
)
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> list[RoleResponse]:
    """
    Return all roles that can be assigned to users.

    Requires Admin role. No request body is required.
    """
    result = await db.execute(select(Role).order_by(Role.role_name))
    return [RoleResponse.model_validate(r) for r in result.scalars().all()]
