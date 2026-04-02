import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_mlkit_barcode_scanning/google_mlkit_barcode_scanning.dart';

import '../theme.dart';
import '../services/api/api_service.dart';
import '../models/loans/checkout_request.dart';

class ScanAztecScreen extends ConsumerStatefulWidget {
  const ScanAztecScreen({super.key});

  @override
  ConsumerState<ScanAztecScreen> createState() => _ScanAztecScreenState();
}

class _ScanAztecScreenState extends ConsumerState<ScanAztecScreen> {
  CameraController? _controller;
  late final BarcodeScanner _barcodeScanner;
  bool _isProcessing = false;
  CameraDescription? _cameraDescription;
  bool _isStreaming = false;
  bool _isDisposed = false;
  String? _cameraError;
  DateTime? _lastScanTime;
  int _frameCount = 0;

  @override
  void initState() {
    super.initState();
    _barcodeScanner = BarcodeScanner(formats: [BarcodeFormat.aztec]);
    _initCamera();
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        _cameraError = 'No camera found on this device.';
        if (mounted) setState(() {});
        return;
      }
      _cameraDescription = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );

      _controller = CameraController(
        _cameraDescription!,
        ResolutionPreset.low,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.nv21,
      );

      await _controller!.initialize();
      await _startImageStream();
      if (mounted) setState(() {});
    } catch (e) {
      _cameraError = 'Failed to initialize camera: $e';
      if (mounted) setState(() {});
    }
  }

  Future<void> _startImageStream() async {
    if (!mounted) return;
    if (_controller == null || !_controller!.value.isInitialized) return;
    if (_isStreaming) return;

    _isStreaming = true;
    try {
      await _controller!.startImageStream(_onFrame);
    } catch (e) {
      _isStreaming = false;
      debugPrint('Failed to start image stream: $e');
    }
  }

  Future<void> _stopImageStream() async {
    if (_controller == null || !_isStreaming) return;
    await _controller!.stopImageStream();
    _isStreaming = false;
  }

  Future<void> _onFrame(CameraImage image) async {
    if (_isDisposed || _isProcessing) return;
    if (!mounted) return;
    if (_controller == null || !_controller!.value.isInitialized) return;

    // Throttle: only process every 3rd frame
    _frameCount++;
    if (_frameCount % 3 != 0) return;

    // Throttle: minimum 200ms between scans
    if (_lastScanTime != null) {
      final elapsed = DateTime.now().difference(_lastScanTime!).inMilliseconds;
      if (elapsed < 200) return;
    }

    _isProcessing = true;

    try {
      final inputImage = _inputImageFromCameraImage(image);
      if (inputImage == null) return;

      final barcodes = await _barcodeScanner.processImage(inputImage);

      if (barcodes.isNotEmpty) {
        for (final barcode in barcodes) {
          if (barcode.format == BarcodeFormat.aztec &&
              barcode.rawValue != null &&
              barcode.rawValue!.isNotEmpty) {
            _lastScanTime = DateTime.now();
            await _onAztecDetected(barcode.rawValue!);
            break;
          }
        }
      }
    } catch (e) {
      debugPrint('Aztec scan processing error: $e');
    } finally {
      _isProcessing = false;
    }
  }

  InputImage? _inputImageFromCameraImage(CameraImage image) {
    final camera = _controller?.description;
    if (camera == null) return null;

    final rotation = InputImageRotationValue.fromRawValue(
      camera.sensorOrientation,
    );
    if (rotation == null) return null;

    final inputImageFormat = InputImageFormat.nv21;
    final Uint8List bytes = image.planes[0].bytes;

    return InputImage.fromBytes(
      bytes: bytes,
      inputImageData: InputImageData(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        imageRotation: rotation,
        inputImageFormat: inputImageFormat,
        planeData: image.planes
            .map((plane) => InputImagePlaneMetadata(
                  bytesPerRow: plane.bytesPerRow,
                  width: plane.width,
                  height: plane.height,
                ))
            .toList(),
      ),
    );
  }

  Future<void> _onAztecDetected(String value) async {
    await _stopImageStream();
    if (!mounted) return;

    debugPrint('Aztec code detected: $value');

    if (kDebugMode) {
      await _showDebugDialog(value);
    } else {
      await _processCheckout(value);
    }
  }

  Future<void> _showDebugDialog(String value) async {
    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Row(
          children: [
            Icon(Icons.qr_code, color: AppColors.accent),
            const SizedBox(width: 8),
            const Text('Aztec Code Scanned'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.primary),
              ),
              child: SelectableText(
                value,
                style: TextStyle(
                  color: AppColors.accent,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  fontFamily: 'monospace',
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Scanned at ${DateTime.now().toIso8601String()}',
              style: TextStyle(color: AppColors.text, fontSize: 12),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              _resumeScanning();
            },
            child: Text('Continue Scanning', style: TextStyle(color: AppColors.text)),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.of(context).pop();
              _processCheckout(value);
            },
            child: const Text('Use Code'),
          ),
        ],
      ),
    );
  }

  Future<void> _processCheckout(String aztecCode) async {
    if (!mounted) return;

    setState(() => _isProcessing = true);

    try {
      final client = ref.read(apiClientProvider);
      final idempotencyKey = _generateIdempotencyKey();

      final response = await client.checkout(
        CheckoutRequest(aztecCode: aztecCode),
        idempotencyKey,
      );

      if (!mounted) return;

      // Navigate to return status with the loan ID
      context.go('/return-status/${response.loanId}');
    } catch (e) {
      if (!mounted) return;

      // Show error dialog
      await showDialog(
        context: context,
        builder: (_) => AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text('Checkout Failed'),
          content: Text('Error: ${e.toString()}'),
          actions: [
            ElevatedButton(
              onPressed: () {
                Navigator.of(context).pop();
                _resumeScanning();
              },
              child: const Text('Try Again'),
            ),
          ],
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _isProcessing = false);
      }
    }
  }

  Future<void> _resumeScanning() async {
    if (_isDisposed || !mounted) return;
    if (_controller == null || !_controller!.value.isInitialized) return;
    await _startImageStream();
  }

  String _generateIdempotencyKey() {
    final random = DateTime.now().millisecondsSinceEpoch;
    return random.toRadixString(16);
  }

  @override
  void dispose() {
    _isDisposed = true;
    _barcodeScanner.close();
    final controller = _controller;
    if (controller != null) {
      _stopImageStream().whenComplete(controller.dispose);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized) {
      return Scaffold(
        backgroundColor: AppColors.background,
        body: Center(
          child: _cameraError != null
              ? Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _cameraError!,
                    style: TextStyle(color: AppColors.text),
                    textAlign: TextAlign.center,
                  ),
                )
              : const CircularProgressIndicator(),
        ),
      );
    }

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Stack(
        children: [
          Positioned.fill(
            child: CameraPreview(_controller!),
          ),
          Center(
            child: Container(
              width: 300,
              height: 300,
              decoration: BoxDecoration(
                border: Border.all(
                  color: Colors.white.withAlpha(138),
                  width: 3,
                ),
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          Positioned(
            left: 16,
            top: 16,
            child: Container(
              decoration: BoxDecoration(
                color: Colors.black.withAlpha(128),
                borderRadius: BorderRadius.circular(8),
              ),
              child: IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: () => context.go('/catalog'),
              ),
            ),
          ),
          if (kDebugMode)
            Positioned(
              right: 16,
              top: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.accent.withAlpha(200),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Text(
                  'DEBUG',
                  style: TextStyle(
                    color: Colors.black,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ),
          Positioned(
            left: 16,
            bottom: 16,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.black.withAlpha(180),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    _isStreaming ? Icons.camera_alt : Icons.camera_alt_outlined,
                    color: _isStreaming ? Colors.green : Colors.grey,
                    size: 16,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    _isProcessing ? 'Processing...' : (_isStreaming ? 'Scanning...' : 'Starting...'),
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
