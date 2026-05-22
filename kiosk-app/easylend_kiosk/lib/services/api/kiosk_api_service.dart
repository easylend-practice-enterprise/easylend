import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../core/app_exceptions.dart';
import '../../core/config.dart';
import '../../core/constants.dart';
import '../../models/assets/asset.dart';
import '../../models/assets/asset_list_response.dart';
import '../../models/loans/checkout_request.dart';
import '../../models/loans/return_initiate_request.dart';

class KioskApiService {
  late final Dio _dio;
  late final FlutterSecureStorage _storage;

  KioskApiService({Dio? dio, FlutterSecureStorage? storage}) {
    _storage =
        storage ??
        FlutterSecureStorage(
          aOptions: AndroidOptions(encryptedSharedPreferences: true),
          iOptions: IOSOptions(
            accessibility: KeychainAccessibility.first_unlock,
          ),
        );

    if (dio != null) {
      _dio = dio;
    } else {
      _dio = Dio(
        BaseOptions(
          baseUrl: AppConfig.baseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 30),
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
        ),
      );
      _dio.interceptors.add(_AuthInterceptor(_dio, _storage));
    }
  }

  Future<String?> _getAccessToken() async {
    return _storage.read(key: StorageKeys.accessToken);
  }

  Future<void> login(String nfcTagId, String pin) async {
    try {
      final response = await _dio.post(
        '/auth/pin',
        data: {'nfc_tag_id': nfcTagId, 'pin': pin},
      );

      final tokenResponse = TokenResponse.fromJson(response.data);
      await _storage.write(
        key: StorageKeys.accessToken,
        value: tokenResponse.accessToken,
      );
      await _storage.write(
        key: StorageKeys.refreshToken,
        value: tokenResponse.refreshToken,
      );
    } on DioException catch (e) {
      throw _handleDioError(e);
    }
  }

  Future<List<Asset>> fetchAvailableAssets() async {
    try {
      final token = await _getAccessToken();
      final response = await _dio.get(
        '/assets',
        queryParameters: {'asset_status': 'AVAILABLE', 'skip': 0, 'limit': 100},
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );

      final assetListResponse = AssetListResponse.fromJson(response.data);
      return assetListResponse.items;
    } on DioException catch (e) {
      throw _handleDioError(e);
    }
  }

  Future<void> checkoutAsset(String aztecCode) async {
    try {
      final token = await _getAccessToken();
      final idempotencyKey = DateTime.now().millisecondsSinceEpoch.toString();
      final response = await _dio.post(
        '/loans/checkout',
        data: CheckoutRequest(aztecCode: aztecCode).toJson(),
        options: Options(
          headers: {
            'Authorization': 'Bearer $token',
            'Idempotency-Key': idempotencyKey,
          },
        ),
      );
      if (response.statusCode != 202) {
        throw AppException('Checkout failed. Please try again.');
      }
    } on DioException catch (e) {
      throw _handleDioError(e);
    }
  }

  Future<void> initiateReturn(String aztecCode) async {
    final kioskId = await _storage.read(key: StorageKeys.kioskId);
    if (kioskId == null || kioskId.isEmpty) {
      throw const AppException(
        'Kiosk is not properly configured. Missing Kiosk ID.',
      );
    }

    try {
      final token = await _getAccessToken();
      final idempotencyKey = DateTime.now().millisecondsSinceEpoch.toString();
      final response = await _dio.post(
        '/loans/return/initiate',
        data: ReturnInitiateRequest(
          aztecCode: aztecCode,
          kioskId: kioskId,
        ).toJson(),
        options: Options(
          headers: {
            'Authorization': 'Bearer $token',
            'Idempotency-Key': idempotencyKey,
          },
        ),
      );
      if (response.statusCode != 202) {
        throw AppException('Return initiation failed. Please try again.');
      }
    } on DioException catch (e) {
      throw _handleDioError(e);
    }
  }

  Future<void> logout() async {
    final refreshToken = await _storage.read(key: StorageKeys.refreshToken);
    if (refreshToken != null) {
      try {
        await _dio.post('/auth/logout', data: {'refresh_token': refreshToken});
      } catch (_) {}
    }
    await _storage.deleteAll();
  }

  AppException _handleDioError(DioException e) {
    final statusCode = e.response?.statusCode;

    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.sendTimeout ||
        e.type == DioExceptionType.receiveTimeout ||
        e.type == DioExceptionType.connectionError) {
      return AppException.networkError();
    }

    if (statusCode != null) {
      if (statusCode >= 500) {
        return AppException.serverError();
      }
      if (statusCode == 400 || statusCode == 404 || statusCode == 409) {
        final data = e.response?.data;
        if (data is Map && data.containsKey('detail')) {
          return AppException(data['detail'].toString(), code: statusCode);
        }
        return AppException.clientError(statusCode);
      }
    }

    return AppException('An error occurred. Please try again.');
  }
}

class TokenResponse {
  final String accessToken;
  final String refreshToken;
  final String tokenType;

  TokenResponse({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'Bearer',
  });

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
    accessToken: json['access_token'] as String,
    refreshToken: json['refresh_token'] as String,
    tokenType: json['token_type'] as String? ?? 'Bearer',
  );
}

class _AuthInterceptor extends Interceptor {
  final Dio _dio;
  final FlutterSecureStorage _storage;

  _AuthInterceptor(this._dio, this._storage);

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode != 401) {
      handler.next(err);
      return;
    }

    try {
      final refreshToken = await _storage.read(key: StorageKeys.refreshToken);
      if (refreshToken == null) {
        handler.next(err);
        return;
      }

      final refreshDio = Dio(
        BaseOptions(
          baseUrl: AppConfig.baseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 30),
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
        ),
      );

      final response = await refreshDio.post(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );

      final tokenResponse = TokenResponse.fromJson(response.data);
      await _storage.write(
        key: StorageKeys.accessToken,
        value: tokenResponse.accessToken,
      );
      await _storage.write(
        key: StorageKeys.refreshToken,
        value: tokenResponse.refreshToken,
      );

      final opts = err.requestOptions;
      opts.headers['Authorization'] = 'Bearer ${tokenResponse.accessToken}';
      _dio.fetch(opts);
    } catch (_) {
      handler.next(err);
    }
  }
}
