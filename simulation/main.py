import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from core import DigitalTwin

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
WS_URL = os.environ.get(
    "VISIONBOX_WS_URL",
    "ws://localhost:8000/ws/visionbox/00000000-0000-0000-0000-000000000000",
)
ANALYZE_URL = os.environ.get(
    "VISION_ANALYZE_URL", "http://localhost:8000/api/v1/vision/analyze"
)
TOKEN = os.environ.get("SIMULATION_API_KEY", "local-dev-sim-key-123")
ADMIN_TOKEN = os.environ.get("ADMIN_API_TOKEN", "admin-secret-token")

# ---------------------------------------------------------------------------
# Twin setup
# ---------------------------------------------------------------------------
twin = DigitalTwin(WS_URL, ANALYZE_URL, TOKEN)
event_queue: asyncio.Queue[str] = asyncio.Queue()


async def notify_ui(msg: str = "update"):
    """Callback for state changes and system logs."""
    await event_queue.put(msg)


twin.on_state_change = notify_ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(twin.connect())
    yield
    task.cancel()


app = FastAPI(title="EasyLend Digital Twin Lab", lifespan=lifespan)


def _admin_headers(x_admin_token: str | None = Header(None)) -> dict[str, str]:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return {"Authorization": f"Bearer {x_admin_token}"} if x_admin_token else {}


def _device_headers() -> dict[str, str]:
    return {"X-Device-Token": TOKEN}


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    return FileResponse("index.html")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@app.get("/state")
async def get_state():
    return twin.get_state()


# ---------------------------------------------------------------------------
# Slot controls
# ---------------------------------------------------------------------------


@app.post("/slot/open")
async def manual_open():
    twin.slot_open = True
    await notify_ui("update")
    return {"status": "ok"}


@app.post("/slot/close")
async def manual_close():
    await twin.close_slot()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


@app.get("/events")
async def event_stream(request: Request):
    async def generator():
        while True:
            if await request.is_disconnected():
                logger.info("SSE Client disconnected.")
                break
            try:
                msg = await asyncio.wait_for(event_queue.get(), timeout=2.0)

                if msg == "update":
                    state = twin.get_state()
                    slot_state = "open" if state["slot_open"] else "closed"
                    led_state = "aan" if state["led_aan"] else "uit"
                    led_color = state.get("led_color", "off")
                    yield f"data: slot:{slot_state}\n\n"
                    yield f"data: led:{led_state}:{state['helderheid']}\n\n"
                    yield f"data: led_color:{led_color}\n\n"
                else:
                    yield f"data: {msg}\n\n"

            except TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Admin: Seed database
# ---------------------------------------------------------------------------


@app.post("/admin/seed")
async def seed_database(x_admin_token: str | None = Header(None)):
    """Run the backend seed script directly (imports backend DB models)."""
    _admin_headers(x_admin_token)
    logger.info("Running database seed via simulation admin endpoint...")

    # Dynamically import and run the backend seed function
    try:
        # Add backend/api to path so we can import the seed script
        backend_path = os.path.join(os.path.dirname(__file__), "..", "backend", "api")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)

        from scripts.seed import seed_database as run_seed  # type: ignore[reportMissingImports]  # noqa: I001

        await run_seed()
        logger.info("Database seeding completed successfully.")
        return {"status": "ok", "message": "Database seeded successfully."}
    except Exception as e:
        logger.error(f"Seed failed: {e}")
        raise HTTPException(status_code=500, detail=f"Seed failed: {e}")


# ---------------------------------------------------------------------------
# Admin: Get full state (kiosks, lockers, assets, loans)
# ---------------------------------------------------------------------------


@app.get("/admin/state")
async def get_admin_state(x_admin_token: str | None = Header(None)):
    """Fetch current kiosks, lockers, assets from the backend API."""
    _admin_headers(x_admin_token)
    headers = _device_headers()

    async with httpx.AsyncClient() as client:
        try:
            kiosks_resp = await client.get(
                f"{BACKEND_URL}/api/v1/kiosks", headers=headers, timeout=10.0
            )
            assets_resp = await client.get(
                f"{BACKEND_URL}/api/v1/assets", headers=headers, timeout=10.0
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Backend unavailable: {e}")

    return {
        "twin_state": twin.get_state(),
        "kiosks": kiosks_resp.json() if kiosks_resp.status_code == 200 else [],
        "assets": assets_resp.json() if assets_resp.status_code == 200 else [],
    }


# ---------------------------------------------------------------------------
# Admin: Create kiosk
# ---------------------------------------------------------------------------


class KioskCreate(BaseModel):
    name: str
    location_description: str = ""


@app.post("/api/v1/kiosks")
async def create_kiosk(payload: KioskCreate, x_admin_token: str | None = Header(None)):
    """Create a new kiosk via the backend API."""
    _admin_headers(x_admin_token)
    headers = _device_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_URL}/api/v1/kiosks",
                json=payload.model_dump(),
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code not in (200, 201):
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Backend unavailable: {e}")


# ---------------------------------------------------------------------------
# Admin: Create locker
# ---------------------------------------------------------------------------


class LockerCreate(BaseModel):
    kiosk_id: str
    logical_number: int
    locker_status: str = "AVAILABLE"


@app.post("/api/v1/lockers")
async def create_locker(
    payload: LockerCreate, x_admin_token: str | None = Header(None)
):
    """Create a new locker via the backend API."""
    _admin_headers(x_admin_token)
    headers = _device_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_URL}/api/v1/lockers",
                json=payload.model_dump(),
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code not in (200, 201):
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Backend unavailable: {e}")


# ---------------------------------------------------------------------------
# Admin: Create asset
# ---------------------------------------------------------------------------


class AssetCreate(BaseModel):
    name: str
    aztec_code: str
    category_id: str
    locker_id: str | None = None
    asset_status: str = "AVAILABLE"


@app.post("/api/v1/assets")
async def create_asset(payload: AssetCreate, x_admin_token: str | None = Header(None)):
    """Create a new asset via the backend API."""
    _admin_headers(x_admin_token)
    headers = _device_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_URL}/api/v1/assets",
                json=payload.model_dump(),
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code not in (200, 201):
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Backend unavailable: {e}")


# ---------------------------------------------------------------------------
# Kiosk flow: Checkout
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    aztec_code: str


@app.post("/loans/checkout")
async def checkout(payload: CheckoutRequest, x_admin_token: str | None = Header(None)):
    """Trigger a checkout flow via the backend API (simulates kiosk scan)."""
    _admin_headers(x_admin_token)
    headers = _device_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_URL}/api/v1/loans/checkout",
                json={"aztec_code": payload.aztec_code},
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code == 202:
                data = resp.json()
                # Store loan_id on the twin so close_slot can use it
                twin.current_loan_id = data.get("loan_id")
                twin.current_eval_type = "CHECKOUT"
                return data
            else:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Backend unavailable: {e}")


# ---------------------------------------------------------------------------
# Kiosk flow: Return initiate
# ---------------------------------------------------------------------------


class ReturnInitiateRequest(BaseModel):
    aztec_code: str


@app.post("/loans/return/initiate")
async def return_initiate(
    payload: ReturnInitiateRequest, x_admin_token: str | None = Header(None)
):
    """Trigger a return flow via the backend API."""
    _admin_headers(x_admin_token)
    headers = _device_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_URL}/api/v1/loans/return/initiate",
                json={"aztec_code": payload.aztec_code},
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code == 202:
                data = resp.json()
                twin.current_loan_id = data.get("loan_id")
                twin.current_eval_type = "RETURN"
                return data
            else:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Backend unavailable: {e}")


# ---------------------------------------------------------------------------
# Kiosk flow: Close slot (triggers vision analyze)
# ---------------------------------------------------------------------------


@app.post("/loans/close")
async def close_loan_slot(x_admin_token: str | None = Header(None)):
    """Simulate door closure after a loan (checkout or return) - triggers AI analyze."""
    _admin_headers(x_admin_token)
    await twin.close_slot()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Locker status override (admin)
# ---------------------------------------------------------------------------


class LockerStatusUpdate(BaseModel):
    locker_status: str


@app.patch("/api/v1/lockers/{locker_id}/status")
async def update_locker_status(
    locker_id: str,
    payload: LockerStatusUpdate,
    x_admin_token: str | None = Header(None),
):
    """Update a locker's status via the backend API."""
    _admin_headers(x_admin_token)
    headers = _device_headers()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.patch(
                f"{BACKEND_URL}/api/v1/lockers/{locker_id}/status",
                json=payload.model_dump(),
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Backend unavailable: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)  # noqa: S104
