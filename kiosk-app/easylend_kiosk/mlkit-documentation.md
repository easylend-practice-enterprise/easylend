# Google ML Kit Barcode Scanning (Aztec) — Documentation

How the scanner works (implementation notes)

- The screen `lib/screens/scan_aztec_screen.dart` uses the `camera` plugin to obtain a continuous `CameraImage` stream.
- Each `CameraImage` is converted to a single byte buffer and wrapped in an `InputImage` with `InputImageData` (size, rotation, format, plane metadata).
- `google_mlkit_barcode_scanning.BarcodeScanner` is configured to look only for `BarcodeFormat.aztec` for performance.
- When a barcode is detected, scanning pauses, an alert dialog shows the decoded value, and the stream restarts afterwards.

Performance and reliability tips

- Only analyze necessary formats (we configured Aztec only) to reduce CPU usage.
- Use `ResolutionPreset.medium` or `low` to reduce frame size for faster processing on low-end devices.
- Throttle processing (the implementation guards with `_isDetecting` to avoid parallel calls).
- Test on target devices (different sensors and orientations affect rotation handling).

Troubleshooting

- If `InputImageRotationValue.fromRawValue(...)` returns `null`, you may need to inspect camera `sensorOrientation` and map it manually.
- If scanning returns no results: verify camera permission, inspect image format (YUV420 vs NV21), and test with sample Aztec images.
- On some devices the `camera` plugin uses different `ImageFormatGroup` values—ensure `InputImageFormatValue.fromRawValue(image.format.raw)` resolves correctly.

Extending the scanner

- To trigger API calls on detection, replace the `showDialog` in `_onAztecDetected` with your network call (e.g., call `POST /api/v1/loans/return/initiate` with the scanned payload).
- Add haptic/visual feedback on successful detection.

Security and privacy

- Do not send raw camera frames to servers. Only send decoded barcode values and minimal metadata.
- Ensure access tokens are used for any calls to backend APIs.
Sample usage
- From the Screen Switcher: open "Scan Aztec" to start the live scanner.
