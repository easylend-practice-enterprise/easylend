from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_title: str = "EasyLend Vision API"
    app_description: str = "AI Vision Service for object detection and segmentation"
    app_version: str = "1.0.0"

    vision_api_key: str | None = None
    skip_model_loading: bool = False

    detection_model_path: str = "models/detection.pt"
    segmentation_model_path: str = "models/segmentation.pt"

    max_upload_size: int = 10 * 1024 * 1024
    pil_max_pixels: int = 100_000_000
    max_image_pixels: int = 50_000_000
    max_model_download_size_bytes: int = 200 * 1024 * 1024

    model_inference_image_size: int = 640
    model_download_chunk_size_bytes: int = 8192
    model_download_timeout_seconds: int = 60
    model_download_user_agent: str = "EasyLend-Vision-Bot"

    https_default_port: int = 443
    restart_delay_seconds: int = 2

    allowed_image_content_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
    )

    model_file_extension: str = ".pt"
    openvino_export_suffix: str = "_openvino_model"
    backup_suffix: str = ".backup"
    temp_suffix: str = ".tmp"
