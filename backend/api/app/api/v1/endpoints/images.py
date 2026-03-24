import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.core.uploads import UPLOAD_DIR
from app.db.models import User

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/{filename}")
async def get_image(
    filename: str,
    _: User = Depends(get_current_user),
):
    """Serve an uploaded image by filename. Enforces strict UUID format."""
    # 1. Strict allowlist validation (UUID hex + image extension)
    if not re.match(r"^[a-f0-9]{32}\.(jpg|png|webp)$", filename):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    file_path = (UPLOAD_DIR / filename).resolve()

    # 2. Path Traversal prevention (defense in depth)
    if not file_path.is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    # 3. File existence check
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    return FileResponse(file_path)
