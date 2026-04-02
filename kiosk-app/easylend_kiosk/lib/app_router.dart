import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'providers/providers.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/pin_entry_screen.dart';
import 'screens/dashboard/asset_catalog_screen.dart';
import 'screens/dashboard/return_status_screen.dart';
import 'screens/scan_aztec_screen.dart';
import 'screens/lending_complete_screen.dart';
import 'screens/shell/screen_switcher.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final isAuthenticated = ref.watch(isAuthenticatedProvider);

  return GoRouter(
    initialLocation: '/login',
    redirect: (context, state) {
      final loggingIn = state.matchedLocation == '/login' ||
          state.matchedLocation == '/pin';

      // If not authenticated and not on login/pin screen, redirect to login
      if (!isAuthenticated && !loggingIn) {
        return '/login';
      }

      // If authenticated and on login screen, redirect to catalog
      if (isAuthenticated && loggingIn) {
        return '/catalog';
      }

      return null;
    },
    routes: [
      // Login flow (public)
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/pin/:nfcTagId',
        name: 'pin',
        builder: (context, state) {
          final nfcTagId = state.pathParameters['nfcTagId'] ?? '';
          return PinEntryScreen(nfcTagId: nfcTagId);
        },
      ),

      // Main app flow (requires auth)
      GoRoute(
        path: '/catalog',
        name: 'catalog',
        builder: (context, state) => const AssetCatalogScreen(),
      ),
      GoRoute(
        path: '/scan',
        name: 'scan',
        builder: (context, state) {
          // In the future, pass assetId from catalog selection
          return const ScanAztecScreen();
        },
      ),
      GoRoute(
        path: '/return-status/:loanId',
        name: 'return-status',
        builder: (context, state) {
          final loanId = state.pathParameters['loanId'] ?? '';
          return ReturnStatusScreen(loanId: loanId);
        },
      ),
      GoRoute(
        path: '/lending-complete',
        name: 'lending-complete',
        builder: (context, state) {
          // Pass loan data via extra
          final extra = state.extra as Map<String, dynamic>?;
          return LendingCompleteScreen(
            loanId: extra?['loanId'] as String?,
          );
        },
      ),

      // Debug screen switcher (only in debug mode)
      GoRoute(
        path: '/debug',
        name: 'debug',
        builder: (context, state) => const ScreenSwitcher(),
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 64, color: Colors.red),
            const SizedBox(height: 16),
            Text('Page not found: ${state.matchedLocation}'),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => context.go('/catalog'),
              child: const Text('Go to Catalog'),
            ),
          ],
        ),
      ),
    ),
  );
});
