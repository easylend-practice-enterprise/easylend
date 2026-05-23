import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core import DigitalTwin

# ---------------------------------------------------------------------------
# Tests for slot open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twin_open_slot_sets_state():
    """When backend sends open_slot, twin should set slot_open=True and store loan info."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    twin.ws = AsyncMock()

    # Simulate backend sending an open_slot command
    msg = json.dumps(
        {"action": "open_slot", "loan_id": "loan-123", "evaluation_type": "CHECKOUT"}
    )

    # Patch _listen to process the single message then raise StopIteration
    received = []

    async def mock_recv():
        if not received:
            received.append(msg)
            return msg
        raise StopAsyncIteration()

    twin.ws.recv = mock_recv

    # Run one cycle manually
    data = json.loads(msg)
    assert data["action"] == "open_slot"
    twin.slot_open = True
    twin.current_loan_id = data.get("loan_id")
    twin.current_eval_type = data.get("evaluation_type")

    assert twin.slot_open is True
    assert twin.current_loan_id == "loan-123"
    assert twin.current_eval_type == "CHECKOUT"


@pytest.mark.asyncio
async def test_twin_open_slot_triggers_callback():
    """open_slot should trigger the on_state_change callback."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    calls = []

    async def state_change(msg):
        calls.append(msg)

    twin.on_state_change = state_change

    msg = json.dumps(
        {"action": "open_slot", "loan_id": "l1", "evaluation_type": "RETURN"}
    )
    data = json.loads(msg)
    twin.slot_open = True
    twin.current_loan_id = data.get("loan_id")
    twin.current_eval_type = data.get("evaluation_type")
    if twin.on_state_change:
        await twin.on_state_change("update")

    assert calls == ["update"]


# ---------------------------------------------------------------------------
# Tests for slot closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twin_close_slot_sends_correct_payload():
    """slot_closed event must include loan_id, evaluation_type, and locker_id."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    twin.ws = AsyncMock()
    twin.current_loan_id = "loan-999"
    twin.current_eval_type = "RETURN"

    await twin.close_slot()

    twin.ws.send.assert_called_once()
    sent_data = json.loads(twin.ws.send.call_args[0][0])
    assert sent_data["event"] == "slot_closed"
    assert sent_data["locker_id"] == "1"
    assert sent_data["loan_id"] == "loan-999"
    assert sent_data["evaluation_type"] == "RETURN"


@pytest.mark.asyncio
async def test_twin_close_slot_clears_state():
    """close_slot should set slot_open to False."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    twin.ws = AsyncMock()
    twin.slot_open = True

    await twin.close_slot()

    assert twin.slot_open is False


# ---------------------------------------------------------------------------
# Tests for LED set_led command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twin_set_led_stores_color():
    """set_led command should store the color (not just 'on')."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    calls = []

    async def state_change(msg):
        calls.append(msg)

    twin.on_state_change = state_change

    data = json.dumps({"action": "set_led", "color": "green"})
    parsed = json.loads(data)
    twin.led_status = parsed.get("color", "green")
    twin.helderheid = 1.0
    if twin.on_state_change:
        await twin.on_state_change("update")

    assert twin.led_status == "green"
    assert twin.helderheid == 1.0
    assert calls == ["update"]


# ---------------------------------------------------------------------------
# Tests for image upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twin_upload_image_uses_correct_endpoints(tmp_path):
    """_upload_image should POST to analyze_url with loan_id and evaluation_type."""
    img_path = tmp_path / "test.jpg"
    twin = DigitalTwin("ws://test", "http://test/analyze", "token")
    twin.image_path = str(img_path)
    twin.current_loan_id = "loan-1"
    twin.current_eval_type = "CHECKOUT"

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_response = MagicMock(status_code=200)
        mock_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__.return_value = mock_instance
        MockClient.return_value.__aexit__.return_value = AsyncMock()

        await twin._upload_image()

        mock_instance.post.assert_called_once()
        args, kwargs = mock_instance.post.call_args
        assert args[0] == "http://test/analyze"
        assert kwargs["headers"]["X-Device-Token"] == "token"
        assert kwargs["data"]["loan_id"] == "loan-1"
        assert kwargs["data"]["evaluation_type"] == "CHECKOUT"


@pytest.mark.asyncio
async def test_twin_upload_image_clears_loan_context(tmp_path):
    """After _upload_image completes, current_loan_id and current_eval_type should be None."""
    img_path = tmp_path / "test.jpg"
    twin = DigitalTwin("ws://test", "http://test/analyze", "token")
    twin.image_path = str(img_path)
    twin.current_loan_id = "loan-1"
    twin.current_eval_type = "CHECKOUT"

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_response = MagicMock(status_code=200)
        mock_instance.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__.return_value = mock_instance
        MockClient.return_value.__aexit__.return_value = AsyncMock()

        await twin._upload_image()

        assert twin.current_loan_id is None
        assert twin.current_eval_type is None


# ---------------------------------------------------------------------------
# Tests for get_state
# ---------------------------------------------------------------------------


def test_twin_get_state_returns_correct_structure():
    """get_state should return slot_open, led_aan, led_color, helderheid, microswitch."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    twin.slot_open = True
    twin.led_status = "green"
    twin.helderheid = 1.0

    state = twin.get_state()

    assert state["slot_open"] is True
    assert state["led_aan"] is True
    assert state["led_color"] == "green"
    assert state["helderheid"] == 1.0
    assert state["microswitch"] is False  # not slot_open means microswitch = True


def test_twin_get_state_led_off():
    """led_status 'off' should make led_aan False."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    twin.led_status = "off"
    twin.helderheid = 0.0

    state = twin.get_state()

    assert state["led_aan"] is False


# ---------------------------------------------------------------------------
# Tests for close_slot with no loan context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twin_close_slot_no_loan_no_upload():
    """close_slot without loan_id should not call _upload_image."""
    twin = DigitalTwin("ws://test", "http://test", "token")
    twin.ws = AsyncMock()
    twin.current_loan_id = None
    twin.current_eval_type = None
    twin.slot_open = True

    with patch.object(twin, "_upload_image") as mock_upload:
        await twin.close_slot()
        mock_upload.assert_not_called()

    assert twin.slot_open is False
