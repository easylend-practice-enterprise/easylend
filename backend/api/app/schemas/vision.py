from pydantic import BaseModel


class DetectionItem(BaseModel):
    class_name: str
    confidence: float


class VisionAnalyzeResponse(BaseModel):
    status: str
    count: int
    detections: list[DetectionItem]
    photo_url: str
