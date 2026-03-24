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
    current_user: User = Depends(get_current_user),
):
    """Serve an uploaded image by filename. Enforces strict UUID format and admin access."""
    # 0. Authorization check: restrict access to admin / privileged users only.
    is_admin = (
        current_user.role is not None and current_user.role.role_name.upper() == "ADMIN"
    )
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access audit images",
        )

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

    # 4. Explicit media type and no-sniff header
    ext = filename.rsplit(".", 1)[-1].lower()
    media_type_map = {
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")

    return FileResponse(
        file_path,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )
