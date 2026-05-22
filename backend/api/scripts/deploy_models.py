import argparse
import asyncio
import os
import sys

import httpx

# Import settings to securely retrieve API keys and ports
from app.core.config import settings


async def deploy_model_action(
    path_or_url: str, model_type: str, api_url: str, is_upload: bool
):
    """Performs the actual deploy or upload action for a single model."""
    headers = {
        "X-Device-Token": settings.VISION_API_KEY,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if is_upload:
                # 1. Local File Upload (POST)
                if not os.path.exists(path_or_url):
                    print(f"Error: local file not found at {path_or_url}")
                    return False

                print(f"Uploading {model_type} model: {path_or_url}...")
                with open(path_or_url, "rb") as f:
                    files = {
                        "file": (
                            os.path.basename(path_or_url),
                            f,
                            "application/octet-stream",
                        )
                    }
                    data = {"model_type": model_type}
                    response = await client.post(
                        f"{api_url}/api/v1/vision/upload-model",
                        headers=headers,
                        data=data,
                        files=files,
                    )
            else:
                # 2. Remote URL Pull (PATCH)
                print(f"Triggering {model_type} pull: {path_or_url}...")
                payload = {f"{model_type}_url": path_or_url}
                response = await client.patch(
                    f"{api_url}/api/v1/vision/update-model",
                    headers=headers,
                    json=payload,
                )

            if response.status_code == 200:
                print(f"  - {model_type.capitalize()} update accepted.")
                return True
            elif response.status_code == 403:
                print(f"  - Auth error: VISION_BOX_API_KEY rejected by {api_url}.")
            else:
                print(f"  - Failed (Status {response.status_code}): {response.text}")

            return False

        except httpx.RequestError as exc:
            print(f"  - Network error connecting to {api_url}: {exc}")
            return False


async def run_deployment(args):
    """Orchestrates multiple model deployments/uploads."""
    api_url = args.api_url.rstrip("/")
    success_count = 0
    total_requested = 0

    print(f"Starting deployment to {api_url}...")
    print("--------------------------------------------------")

    # Handle Detection
    if args.detection:
        total_requested += 1
        is_url = args.detection.startswith(("http://", "https://"))
        if await deploy_model_action(args.detection, "detection", api_url, not is_url):
            success_count += 1

    # Handle Segmentation
    if args.segmentation:
        total_requested += 1
        is_url = args.segmentation.startswith(("http://", "https://"))
        if await deploy_model_action(
            args.segmentation, "segmentation", api_url, not is_url
        ):
            success_count += 1

    print("--------------------------------------------------")
    if total_requested > 0:
        if success_count == total_requested:
            print(
                f"Deployment complete. {success_count}/{total_requested} models accepted."
            )
            print("Vision service will restart automatically after processing.")
        else:
            print(
                f"Deployment partial/failed. {success_count}/{total_requested} models accepted."
            )
            sys.exit(1)
    else:
        print("Error: must provide at least one model path or URL.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="EasyLend model deployment utility")
    parser.add_argument(
        "-d",
        "--detection",
        type=str,
        help="Local path or HTTPS URL for the Detection model (.pt)",
    )
    parser.add_argument(
        "-s",
        "--segmentation",
        type=str,
        help="Local path or HTTPS URL for the Segmentation model (.pt)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://127.0.0.1:8000",
        help="Main API base URL (default: http://127.0.0.1:8000)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(run_deployment(args))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
