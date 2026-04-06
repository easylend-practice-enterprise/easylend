import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/auth/user.dart';
import '../../models/auth/refresh_token_request.dart';
import 'api_client.dart';
import '../local/secure_storage_service.dart';

// Base URL - in production this would come from environment config
const _baseUrl = 'http://10.0.2.2:8000'; // Android emulator localhost

final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(BaseOptions(
    baseUrl: _baseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 30),
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
  ));

  // Auth interceptor for attaching tokens
  dio.interceptors.add(AuthInterceptor(ref));
  // Log interceptor for debugging - only in debug mode to avoid leaking sensitive data
  if (kDebugMode) {
    dio.interceptors.add(LogInterceptor(
      requestBody: true,
      responseBody: true,
      error: true,
    ));
  }

  return dio;
});

final apiClientProvider = Provider<ApiClient>((ref) {
  final dio = ref.watch(dioProvider);
  return ApiClient(dio);
});

class AuthInterceptor extends Interceptor {
  final Ref _ref;

  AuthInterceptor(this._ref);

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final storage = _ref.read(secureStorageProvider);
    final token = await storage.getAccessToken();

    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }

    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    // Skip refresh loop for refresh/logout endpoints
    final path = err.requestOptions.path;
    if (path.contains('/auth/refresh') || path.contains('/auth/logout')) {
      return handler.next(err);
    }

    if (err.response?.statusCode == 401) {
      // Try to refresh the token
      final refreshed = await _ref.read(authServiceProvider).refreshToken();
      if (refreshed) {
        // Retry the original request
        final opts = err.requestOptions;
        final storage = _ref.read(secureStorageProvider);
        final token = await storage.getAccessToken();
        opts.headers['Authorization'] = 'Bearer $token';

        final dio = _ref.read(dioProvider);
        try {
          final response = await dio.fetch(opts);
          return handler.resolve(response);
        } catch (e) {
          return handler.next(err);
        }
      }
    }
    handler.next(err);
  }
}

/// Auth state
class AuthState {
  final User? user;
  final bool isAuthenticated;
  final bool isLoading;
  final String? error;

  const AuthState({
    this.user,
    this.isAuthenticated = false,
    this.isLoading = false,
    this.error,
  });

  AuthState copyWith({
    User? user,
    bool? isAuthenticated,
    bool? isLoading,
    String? error,
  }) {
    return AuthState(
      user: user ?? this.user,
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  static const unauthenticated = AuthState();
}

/// Auth service for login/logout/refresh operations
class AuthService {
  final Ref _ref;

  AuthService(this._ref);

  ApiClient get _client => _ref.read(apiClientProvider);
  SecureStorageService get _storage => _ref.read(secureStorageProvider);

  Future<bool> refreshToken() async {
    try {
      final refreshToken = await _storage.getRefreshToken();
      if (refreshToken == null) return false;

      final response = await _client.refreshToken(
        RefreshTokenRequest(refreshToken: refreshToken),
      );

      await _storage.saveTokens(
        accessToken: response.accessToken,
        refreshToken: response.refreshToken,
      );

      return true;
    } catch (e) {
      await _storage.clearAll();
      return false;
    }
  }

  Future<void> logout() async {
    try {
      final refreshToken = await _storage.getRefreshToken();
      if (refreshToken != null) {
        await _client.logout(RefreshTokenRequest(refreshToken: refreshToken));
      }
    } catch (_) {
      // Ignore logout errors - we clear tokens anyway
    } finally {
      await _storage.clearAll();
    }
  }
}

final authServiceProvider = Provider<AuthService>((ref) {
  return AuthService(ref);
});
