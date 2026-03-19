import 'dart:async';
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import '../theme.dart';
import 'package:google_mlkit_barcode_scanning/google_mlkit_barcode_scanning.dart';

class ScanAztecScreen extends StatefulWidget {
  const ScanAztecScreen({super.key});

  @override
  State<ScanAztecScreen> createState() => _ScanAztecScreenState();
}

class _ScanAztecScreenState extends State<ScanAztecScreen> {
  CameraController? _controller;
  late final BarcodeScanner _barcodeScanner;
  bool _isDetecting = false;
  CameraDescription? _cameraDescription;
  bool _isStreaming = false;
  bool _isDisposed = false;
  String? _cameraError;

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
        const errorMessage = 'No camera found on this device.';
        _cameraError = errorMessage;
        if (mounted) {
          setState(() {});
        }
        return;
      }
      // prefer back camera
      _cameraDescription = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      _controller = CameraController(
        _cameraDescription!,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await _controller!.initialize();
      await _startImageStream();
      if (mounted) setState(() {});
    } catch (e) {
      if (mounted) {
        setState(() {
          _cameraError = 'Failed to initialize camera: $e';
        });
      } else {
        _cameraError = 'Failed to initialize camera: $e';
      }
    }
  }

  Future<void> _startImageStream() async {
    if (_controller == null || !_controller!.value.isInitialized) return;
    if (_isStreaming) return;

    await _controller!.startImageStream(_captureAndProcess);
    _isStreaming = true;
  }

  Future<void> _stopImageStream() async {
    if (_controller == null) return;
    if (!_isStreaming) return;

    await _controller!.stopImageStream();
    _isStreaming = false;
  }

  Future<void> _captureAndProcess(CameraImage image) async {
    if (_isDisposed || _isDetecting) return;
    if (_controller == null || !_controller!.value.isInitialized) return;
    _isDetecting = true;
    try {
      final inputImage = _inputImageFromCameraImage(image);
      if (inputImage == null) return;
      final barcodes = await _barcodeScanner.processImage(inputImage);
      if (barcodes.isNotEmpty) {
        for (final b in barcodes) {
          if (b.format == BarcodeFormat.aztec && b.rawValue != null) {
            await _onAztecDetected(b.rawValue!);
            break;
          }
        }
      }
    } catch (e) {
      if (mounted) {
        debugPrint('Aztec scan processing error: $e');
      }
    } finally {
      _isDetecting = false;
    }
  }

  InputImage? _inputImageFromCameraImage(CameraImage image) {
    final camera = _controller?.description;
    if (camera == null) return null;

    final rotation = InputImageRotationValue.fromRawValue(
      camera.sensorOrientation,
    );
    final format = InputImageFormatValue.fromRawValue(image.format.raw);
    if (rotation == null || format == null) return null;

    final allBytes = BytesBuilder(copy: false);
    for (final plane in image.planes) {
      allBytes.add(plane.bytes);
    }

    return InputImage.fromBytes(
      bytes: allBytes.takeBytes(),
      inputImageData: InputImageData(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        imageRotation: rotation,
        inputImageFormat: format,
        planeData: image.planes
            .map(
              (plane) => InputImagePlaneMetadata(
                bytesPerRow: plane.bytesPerRow,
                width: plane.width,
                height: plane.height,
              ),
            )
            .toList(),
      ),
    );
  }

  Future<void> _onAztecDetected(String value) async {
    await _stopImageStream();
    if (!mounted) return;
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Aztec code'),
        content: Text(value),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
    if (!mounted) return;
    if (_controller == null || !_controller!.value.isInitialized) return;
    await _startImageStream();
  }

  @override
  void dispose() {
    _isDisposed = true;
    _barcodeScanner.close();
    final controller = _controller;
    if (controller != null) {
      unawaited(_stopImageStream().whenComplete(controller.dispose));
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
              ? Text(
                  _cameraError!,
                  style: TextStyle(color: AppColors.text),
                  textAlign: TextAlign.center,
                )
              : const CircularProgressIndicator(),
        ),
      );
    }

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Stack(
          children: [
            CameraPreview(_controller!),
            Positioned.fill(
              child: Center(
                child: Container(
                  width: 300,
                  height: 300,
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: AppColors.divider.withAlpha(138),
                      // 54% transparency for the scanning reticle ^
                      width: 3,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            Positioned(
              left: 16,
              top: 16,
              child: IconButton(
                icon: Icon(Icons.close, color: AppColors.divider),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
