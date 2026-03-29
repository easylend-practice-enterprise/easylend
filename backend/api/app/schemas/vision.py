from pydantic import BaseModel


class DetectionItem(BaseModel):
    class_name: str
    confidence: float


class VisionAnalyzeResponse(BaseModel):
    status: str
    count: int
    detections: list[DetectionItem]
    photo_url: str


class ModelUpdateRequest(BaseModel):
    object_detection_url: str
    segmentation_url: str


class ModelUpdateResponse(BaseModel):
    message: str
