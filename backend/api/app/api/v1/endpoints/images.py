from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.db.models import User

router = APIRouter(prefix="/images", tags=["images"])
UPLOAD_DIR = Path("uploads")


@router.get("/{filename}")
async def get_image(
    filename: str,
    _: User = Depends(get_current_user),
):
    """Serve an uploaded image by filename."""
    file_path = (UPLOAD_DIR / filename).resolve()

    # Path Traversal preventie
    if not file_path.is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename"
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    return FileResponse(file_path)
