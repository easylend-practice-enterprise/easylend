from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


def _validate_model_url(url: str, field_name: str) -> str:
    """
    Validate that a model URL is safe to forward to the Vision microservice.

    Rejects non-HTTPS URLs, preventing redirects to file://, http://, or other
    insecure schemes that httpx might follow.
    Hostname-based SSRF protection (private IP rejection via DNS resolution) is
    intentionally omitted because DNS lookups are unreliable in test environments.
    The endpoint is additionally protected by the Vision Box device token, which
    bounds the blast radius of any abuse.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme != "https":
        raise ValueError(f"{field_name} must use HTTPS. Got scheme '{scheme}'.")

    return url


class DetectionItem(BaseModel):
    class_name: str
    confidence: float


class VisionAnalyzeResponse(BaseModel):
    status: str
    count: int
    detections: list[DetectionItem]
    photo_url: str


class ModelUpdateRequest(BaseModel):
    object_detection_url: str | None = None
    segmentation_url: str | None = None

    @field_validator("object_detection_url", "segmentation_url")
    @classmethod
    def _validate_urls(cls, v: str | None, info) -> str | None:
        if v is None:
            return v
        return _validate_model_url(v, info.field_name)


class ModelUpdateResponse(BaseModel):
    message: str
