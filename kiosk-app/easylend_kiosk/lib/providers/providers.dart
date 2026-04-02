import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/auth/user.dart';
import '../models/auth/nfc_login_request.dart';
import '../models/auth/pin_login_request.dart';
import '../models/loans/loan_response.dart';
import '../models/api/error_response.dart';
import '../services/api/api_service.dart';
import '../services/local/secure_storage_service.dart';

// ============================================================================
// Auth State
// ============================================================================

class AuthNotifier extends StateNotifier<AuthState> {
  final Ref _ref;

  AuthNotifier(this._ref) : super(AuthState.unauthenticated) {
    _loadStoredAuth();
  }

  Future<void> _loadStoredAuth() async {
    final storage = _ref.read(secureStorageProvider);
    final userJson = await storage.getUser();

    if (userJson != null) {
      try {
        final user = User.fromJson(jsonDecode(userJson));
        state = AuthState(user: user, isAuthenticated: true);
      } catch (_) {
        await storage.clearAll();
      }
    }
  }

  Future<void> nfcLogin(String nfcTagId) async {
    state = state.copyWith(isLoading: true, error: null);

    try {
      final client = _ref.read(apiClientProvider);
      // NFC login just validates the badge - response indicates success
      // The actual auth happens with PIN
      await client.nfcLogin(NfcLoginRequest(nfcTagId: nfcTagId));
      state = state.copyWith(isLoading: false);
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: _formatError(e),
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<bool> pinLogin(String nfcTagId, String pin) async {
    state = state.copyWith(isLoading: true, error: null);

    try {
      final client = _ref.read(apiClientProvider);
      final storage = _ref.read(secureStorageProvider);

      final response = await client.pinLogin(
        PinLoginRequest(nfcTagId: nfcTagId, pin: pin),
      );

      await storage.saveTokens(
        accessToken: response.accessToken,
        refreshToken: response.refreshToken,
      );

      // Fetch user profile
      final user = await client.getMe();
      await storage.saveUser(jsonEncode(user.toJson()));

      state = AuthState(user: user, isAuthenticated: true);
      return true;
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: _formatError(e),
      );
      return false;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      return false;
    }
  }

  Future<void> logout() async {
    // Clear auth state immediately for responsive UI
    state = AuthState.unauthenticated;

    // Then clear server-side session (ignore errors - we cleared locally)
    try {
      await _ref.read(authServiceProvider).logout();
    } catch (_) {
      // Ignore logout errors - local state already cleared
    }
  }

  /// Debug login - bypasses NFC/PIN and logs in directly.
  /// ONLY works in debug mode.
  Future<bool> debugLogin(String username, String password) async {
    assert(kDebugMode, 'debugLogin should only be called in debug mode');

    state = state.copyWith(isLoading: true, error: null);

    try {
      // Simulate network delay
      await Future.delayed(const Duration(milliseconds: 500));

      // For debug, we create a mock user based on credentials
      final isAdmin = username == 'admin';
      final user = User(
        userId: isAdmin ? '1' : '2',
        roleId: isAdmin ? '1' : '2',
        roleName: isAdmin ? 'admin' : 'user',
        firstName: username,
        lastName: 'Debug',
        email: '$username@example.com',
        failedLoginAttempts: 0,
        status: 'active',
        acceptedPrivacyPolicy: true,
      );

      await _ref.read(secureStorageProvider).saveUser(user.toJson().toString());
      await _ref.read(secureStorageProvider).saveTokens(
            accessToken: 'debug_access_token_$username',
            refreshToken: 'debug_refresh_token_$username',
          );

      state = AuthState(user: user, isAuthenticated: true);
      return true;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      return false;
    }
  }

  String _formatError(DioException e) {
    if (e.response?.data != null) {
      try {
        final error = ErrorResponse.fromJson(e.response!.data);
        return error.displayMessage;
      } catch (_) {}
    }
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return 'Connection timeout. Please check your network.';
      case DioExceptionType.connectionError:
        return 'Cannot connect to server.';
      default:
        return 'An error occurred. Please try again.';
    }
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(ref);
});

final isAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(authProvider).isAuthenticated;
});

final isAdminProvider = Provider<bool>((ref) {
  final user = ref.watch(authProvider).user;
  return user?.isAdmin ?? false;
});

// ============================================================================
// Catalog
// ============================================================================

final catalogProvider = FutureProvider<List<dynamic>>((ref) async {
  final client = ref.watch(apiClientProvider);
  final response = await client.getCatalog();
  return response;
});

// ============================================================================
// Loan Polling with Exponential Backoff
// ============================================================================

/// Polling interval strategy:
/// - 0-10s: poll every 2 seconds
/// - 10-30s: poll every 5 seconds
/// - 30-45s: poll every 10 seconds
int _getPollingInterval(Duration elapsed) {
  if (elapsed.inSeconds <= 10) return 2;
  if (elapsed.inSeconds <= 30) return 5;
  return 10;
}

class LoanPollingState {
  final String loanId;
  final String? currentStatus;
  final LoanPublicResponse? loan;
  final bool isComplete;
  final bool hasError;
  final String? error;

  const LoanPollingState({
    required this.loanId,
    this.currentStatus,
    this.loan,
    this.isComplete = false,
    this.hasError = false,
    this.error,
  });

  LoanPollingState copyWith({
    String? currentStatus,
    LoanPublicResponse? loan,
    bool? isComplete,
    bool? hasError,
    String? error,
  }) {
    return LoanPollingState(
      loanId: loanId,
      currentStatus: currentStatus ?? this.currentStatus,
      loan: loan ?? this.loan,
      isComplete: isComplete ?? this.isComplete,
      hasError: hasError ?? this.hasError,
      error: error,
    );
  }
}

class LoanPollingNotifier extends StateNotifier<LoanPollingState> {
  final Ref _ref;
  DateTime? _startTime;

  LoanPollingNotifier(this._ref, String loanId)
      : super(LoanPollingState(loanId: loanId));

  Future<void> startPolling() async {
    _startTime = DateTime.now();
    await _poll();
  }

  Future<void> _poll() async {
    if (!mounted) return;
    if (state.isComplete) return;

    try {
      final client = _ref.read(apiClientProvider);
      final response = await client.getLoanStatus(state.loanId);

      state = state.copyWith(currentStatus: response.loanStatus);

      // Check if we're in a terminal state
      if (response.loanStatus == LoanStatus.completed ||
          response.loanStatus == LoanStatus.fraudSuspected ||
          response.loanStatus == LoanStatus.disputed ||
          response.loanStatus == LoanStatus.pendingInspection) {
        state = state.copyWith(isComplete: true);
        return;
      }

      // Schedule next poll
      if (_startTime != null) {
        final elapsed = DateTime.now().difference(_startTime!);
        // Max 45 seconds of polling
        if (elapsed.inSeconds > 45) {
          state = state.copyWith(isComplete: true);
          return;
        }

        final interval = _getPollingInterval(elapsed);
        await Future.delayed(Duration(seconds: interval));
        await _poll();
      }
    } catch (e) {
      state = state.copyWith(hasError: true, error: e.toString());
    }
  }

  void stopPolling() {
    state = state.copyWith(isComplete: true);
  }
}

final loanPollingProvider = StateNotifierProvider.family<LoanPollingNotifier, LoanPollingState, String>(
  (ref, loanId) => LoanPollingNotifier(ref, loanId),
);

// ============================================================================
// Checkout & Return
// ============================================================================
