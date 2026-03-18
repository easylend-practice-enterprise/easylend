import 'dart:async';
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
  Timer? _periodicTimer;

  @override
  void initState() {
    super.initState();
    _barcodeScanner = BarcodeScanner(formats: [BarcodeFormat.aztec]);
    _initCamera();
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
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
      // start periodic capture instead of image stream to avoid format/rotation issues
      _periodicTimer = Timer.periodic(
        const Duration(milliseconds: 800),
        (_) => _captureAndProcess(),
      );
      if (mounted) setState(() {});
    } catch (e) {
      // ignore camera errors for now
    }
  }

  Future<void> _captureAndProcess() async {
    if (_isDetecting) return;
    if (_controller == null || !_controller!.value.isInitialized) return;
    _isDetecting = true;
    try {
      final XFile file = await _controller!.takePicture();
      final inputImage = InputImage.fromFilePath(file.path);
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
      // ignore
    } finally {
      _isDetecting = false;
    }
  }

  Future<void> _onAztecDetected(String value) async {
    // pause periodic captures while showing result
    _periodicTimer?.cancel();
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
    // restart stream
    if (_controller != null) {
      _periodicTimer = Timer.periodic(
        const Duration(milliseconds: 800),
        (_) => _captureAndProcess(),
      );
    }
  }

  @override
  void dispose() {
    _barcodeScanner.close();
    _periodicTimer?.cancel();
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized) {
      return Scaffold(
        backgroundColor: AppColors.background,
        body: const Center(child: CircularProgressIndicator()),
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
                icon: const Icon(Icons.close, color: AppColors.divider),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
