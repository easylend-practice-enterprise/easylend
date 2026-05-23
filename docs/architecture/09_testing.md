## 2.8 Testing and Validation

EasyLend's testing process follows a phased strategy where subsystems are first validated in isolation before being brought together in an integration context. This approach made it possible to isolate defects early while simultaneously verifying interoperability between the different layers of the system.

### 2.8.1 Test Approach

EasyLend's test strategy consists of three layers. The first layer comprises unit tests for individual components: the state machine, the rate limiter, auth guards, and the WebSocket manager. These tests run with mocked dependencies so they execute quickly and deterministically. The second layer involves integration tests with real database containers via testcontainers, where PostgreSQL 17 and Redis are started in an isolated context. This enables end-to-end scenarios such as complete checkout and return flows without mocking the database layer. The third layer consists of manual integration tests on physical hardware: slot openings, camera captures, and WebSocket events are validated live.

The following real-world scenarios were tested: a student retrieves a laptop from a locker and closes the door (checkout flow), a student returns a laptop and the AI detects damage (return flow with damage detection), the system handles a network interruption to the Vision Box (fail-open behavior), and the system blocks a user with outstanding overdue loans at checkout (quota and sanction enforcement).

### 2.8.2 Backend Validation

The REST API was validated through a combination of automated tests and targeted scenarios. The integration tests with testcontainers_postgres and testcontainers_redis provided the ability to traverse the full request lifecycle: authentication with NFC + PIN, sending idempotency keys, locking rows with FOR UPDATE, and publishing WebSocket events. Each of these steps could be verified individually because the tests controlled the exact sequence of database calls via a fake session queue.

An important validation point was the 207 Multi-Status response on hardware failures. In the test `test_checkout_hardware_offline_fallback`, it was verified that when the database commit succeeds but the WebSocket command to the Vision Box fails, the loan retains the RESERVED status and the polling loop continues to function correctly. This fail-open behavior is essential for the system's reliability during network outages.

The rate limiter was validated in `test_rate_limit.py` with scenarios for Redis failures: the tests confirmed that on a Redis timeout, the limiter fails open and allows the request through instead of blocking it. Quota enforcement for loans was verified via `test_checkout_blocked_by_quota_limit` and `test_checkout_blocked_by_overdue_loan`, which respectively checked that a user with two active loans cannot start a third and that outstanding overdue loans result in a block.

Transactions were tested via the state machine tests in `test_state_machine.py`. The state machine validates that illegal transitions (for example from COMPLETED to RESERVED) raise an `InvalidLoanTransitionError`, and that legitimate transitions apply the correct status changes to loan, asset, and locker.

### 2.8.3 Frontend Validation

The kiosk frontend was validated via manual tests on an Android emulator and physical devices in the development environment. The authentication process — NFC badge detection followed by PIN input — was tested with both valid and invalid credentials. The token interceptor was verified by letting the access token expire during an active session and observing that the refresh flow transparently fetched a new token without user interaction.

Navigation between screens was tested for all main flows: browsing the catalog, selecting an item, scanning the Aztec code, confirming checkout, and scanning for return. The polling loop to `/loans/{id}/status` was validated in practice: after a checkout, the backend responds with 202 Accepted and the frontend polls until the status becomes ACTIVE. The double-click protection via idempotency keys was also checked by simulating rapid repeated clicks and verifying that no duplicate reservations were created.

An observation during validation was that the NFC adapter in the development environment only supported mock input strings. The badge UID had to be entered manually as text, which limited the testing of the full NFC authentication flow in the development environment. In production with physical NFC hardware, this would be fully functional.

The idle timeout wrapper was validated by leaving the application idle for 60 seconds and verifying that it automatically logged out and returned to the login screen. This prevents a user who leaves the terminal from leaving an open session behind.

### 2.8.4 AI Validation

AI validation took place within the integration test flow by mocking Vision service HTTP calls with respx. In `test_flow_vision.py`, four scenarios were validated: checkout confirmed (locker opens), checkout with suspected fraud (locker does not open), return confirmed (item present, no damage), and return with damage (item present, damage detected). These tests confirmed that the state machine made the correct transition based on the AI response.

In practice, it was noted that the Vision service inference time varies depending on the load on the Raspberry Pi. The dual-phase approach — where detection and segmentation are called in parallel and the state transition only occurs after both responses arrive — was found to be robust for this variability. Separating the inference phase (without lock) and the commit phase (with fail-fast lock) prevented slower AI calls from holding database resources.

The upload of photos to `/vision/analyze` was validated via the digital twin in the simulation environment, where the correct endpoint, appropriate headers, and loan_id/evaluation_type parameters were checked.

### 2.8.5 Hardware Validation

Hardware integration was validated through a combination of the digital twin simulation and manual tests with physical components.

**Slot opening**: The WebSocket communication between the backend and the Vision Box was tested in `test_ws_send_command.py`. A TestClient websocket connection received the `open_slot` command with the correct locker_id and loan_id payload. The digital twin test `test_twin_open_slot_sets_state` confirmed that upon receiving this command, the `slot_open` flag was set and the loan context was saved.

**GPIO events**: The microswitch detection (slot open/closed) was simulated in the digital twin by manually setting `slot_open` and verifying that `close_slot` sent the correct `slot_closed` event to the backend with the associated metadata.

**Camera capture**: The camera capture flow was validated in the simulation environment via `test_twin_upload_image_uses_correct_endpoints`, which confirmed that the photo was posted to the correct `/analyze` endpoint with the correct `X-Device-Token` authentication header.

**WebSocket events**: The full event protocol — `open_slot`, `slot_closed`, `set_led` — was validated via the digital twin tests. The `slot_closed` event contains the `loan_id`, `evaluation_type`, and `locker_id` fields that the backend needs for the state transition.

**Network interruption**: The fail-open behavior during network outages was tested by breaking the WebSocket connection during an active flow. In that case, the backend responds with 207 Multi-Status and the loan transitions to RESERVED or RETURNING status, where further polling awaits the definitive result. This prevents a network outage from completely blocking the user.

**Fallback behavior**: In scenarios where the Vision Box is unreachable, the system retains the loan in its current status and lets the polling loop continue. The admin can manage the status of such loans via the quarantine dashboard interface once the Vision Box is back online.

### 2.8.6 General Observations and Limitations

The test system had several notable strengths. The combination of fake sessions with predictable call queues made it possible to write complex flow tests without flaky database state. The testcontainers setup with real PostgreSQL and Redis instances gave confidence that the integration with these external services was correct. The separation between inference (without lock) and commit (with lock) in the Vision flow proved to be robust in practice for variability in AI inference speeds.

There were also weaknesses. The fake Redis client in the unit tests had to be manually maintained as new Redis operations were added, which introduced maintenance overhead. The Vision API tests used respx mocking, meaning that actual AI inference was not tested — only the call and response parsing. For complete validation, a representative set of photos with known scenarios would be needed to be presented in an integration test against the Vision service.

The WebSocket hardware tests were limited to the digital twin simulation. The physical GPIO integration on the Raspberry Pi could not be fully automated in the test suite; manual validation was necessary for the complete circuit. This is inherent to hardware integration tests in a development environment.

A limitation that was explicitly experienced was the absence of a test environment for the full hardware stack. The Vision Box software runs on a Raspberry Pi with a specific camera and GPIO setup that cannot be fully simulated. As a result, actual damage detection could only be validated to a limited extent with the available test photos.

Time pressure in the project phase meant that some edge cases were not exhaustively tested, such as the scenario where a user initiates a return twice in quick succession with different Aztec codes, or multiple loans with overdue statuses expiring simultaneously. These scenarios are covered in theory and code but were not captured in an automated test under time pressure.

The integrations that are not yet fully production-ready at the close of the development phase are: full NFC hardware authentication on the kiosk (only mock strings in development), actual damage detection with physical equipment (limited testing with simulated photos), and the watchdog for the overdue worker which has not yet undergone a full load test in production. The backend API itself is robustly tested and the transactional foundation — state transitions, locking, and failover behavior — is validated and ready for production deployment.
