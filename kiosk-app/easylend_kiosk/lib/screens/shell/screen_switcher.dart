import 'package:flutter/material.dart';
import '../auth/login_screen.dart';
import '../dashboard/asset_catalog_screen.dart';
import '../dashboard/return_status_screen.dart';
import '../scan_aztec_screen.dart';
import '../lending_complete_screen.dart';
import '../modals/inactivity_modal.dart';

class ScreenSwitcher extends StatelessWidget {
  const ScreenSwitcher({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Screen Switcher')),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          ElevatedButton(
            onPressed: () => _open(context, const LoginScreen()),
            child: const Text('Login Screen'),
          ),
          ElevatedButton(
            onPressed: () => _open(context, const AssetCatalogScreen()),
            child: const Text('Asset Catalog'),
          ),
          ElevatedButton(
            onPressed: () => _open(context, const ReturnStatusScreen()),
            child: const Text('Return Status'),
          ),
          ElevatedButton(
            onPressed: () => _open(context, const ScanAztecScreen()),
            child: const Text('Scan Aztec'),
          ),
          ElevatedButton(
            onPressed: () => _open(context, const LendingCompleteScreen()),
            child: const Text('Lending Complete'),
          ),
          ElevatedButton(
            onPressed: () => _showModal(context),
            child: const Text('Show Inactivity Modal'),
          ),
        ],
      ),
    );
  }

  void _open(BuildContext context, Widget w) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => w));

  void _showModal(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => InactivityModal(
        onStay: () => Navigator.of(context).pop(),
        onLogout: () => Navigator.of(context).pop(),
      ),
    );
  }
}
