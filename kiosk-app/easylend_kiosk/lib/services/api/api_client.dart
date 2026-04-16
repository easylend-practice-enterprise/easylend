import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../models/auth/nfc_login_request.dart';
import '../../models/auth/pin_login_request.dart';
import '../../models/auth/token_response.dart';
import '../../models/auth/user.dart';
import '../../models/auth/refresh_token_request.dart';
import '../../models/catalog/catalog_item.dart';
import '../../models/loans/checkout_request.dart';
import '../../models/loans/loan_response.dart';
import '../../models/loans/loan_status_response.dart';
import '../../models/loans/return_initiate_request.dart';

class ApiClient {
  final Dio _dio;

  ApiClient(this._dio);

  // Auth endpoints

  Future<void> nfcLogin(NfcLoginRequest request) async {
    await _dio.post('/api/v1/auth/nfc', data: request.toJson());
  }

  Future<TokenResponse> pinLogin(PinLoginRequest request) async {
    final response = await _dio.post('/api/v1/auth/pin', data: request.toJson());
    return TokenResponse.fromJson(response.data);
  }

  Future<TokenResponse> refreshToken(RefreshTokenRequest request) async {
    final response = await _dio.post('/api/v1/auth/refresh', data: request.toJson());
    return TokenResponse.fromJson(response.data);
  }

  Future<void> logout(RefreshTokenRequest request) async {
    await _dio.post('/api/v1/auth/logout', data: request.toJson());
  }

  // User endpoints

  Future<User> getMe() async {
    final response = await _dio.get('/api/v1/users/me');
    return User.fromJson(response.data);
  }

  // Catalog endpoints

  Future<List<CatalogUserView>> getCatalog({int skip = 0, int limit = 100}) async {
    final response = await _dio.get('/api/v1/catalog', queryParameters: {
      'skip': skip,
      'limit': limit,
    });
    final List<dynamic> data = response.data as List<dynamic>;
    return data.map((e) => CatalogUserView.fromJson(e as Map<String, dynamic>)).toList();
  }

  // Loan endpoints

  Future<PaginatedLoansResponse> getLoans({int skip = 0, int limit = 100}) async {
    final response = await _dio.get('/api/v1/loans', queryParameters: {
      'skip': skip,
      'limit': limit,
    });
    return PaginatedLoansResponse.fromJson(response.data);
  }

  Future<LoanStatusResponse> getLoanStatus(String loanId) async {
    final response = await _dio.get('/api/v1/loans/$loanId/status');
    return LoanStatusResponse.fromJson(response.data);
  }

  Future<LoanPublicResponse> checkout(CheckoutRequest request, String? idempotencyKey) async {
    final options = idempotencyKey != null
        ? Options(headers: {'Idempotency-Key': idempotencyKey})
        : null;
    final response = await _dio.post('/api/v1/loans/checkout', data: request.toJson(), options: options);
    return LoanPublicResponse.fromJson(response.data);
  }

  Future<LoanPublicResponse> returnInitiate(ReturnInitiateRequest request, String? idempotencyKey) async {
    final options = idempotencyKey != null
        ? Options(headers: {'Idempotency-Key': idempotencyKey})
        : null;
    final response = await _dio.post('/api/v1/loans/return/initiate', data: request.toJson(), options: options);
    return LoanPublicResponse.fromJson(response.data);
  }

  /// Checks backend connectivity. Returns duration on success, throws on failure.
  /// Only available in debug builds.
  Future<Duration> ping() async {
    assert(kDebugMode, 'ping() should only be called in debug mode');
    final stopwatch = Stopwatch()..start();
    await _dio.get('/api/v1/health');
    stopwatch.stop();
    return stopwatch.elapsed;
  }
}

class PaginatedLoansResponse {
  final List<LoanPublicResponse> items;
  final int total;

  PaginatedLoansResponse({required this.items, required this.total});

  factory PaginatedLoansResponse.fromJson(Map<String, dynamic> json) {
    return PaginatedLoansResponse(
      items: (json['items'] as List).map((e) => LoanPublicResponse.fromJson(e)).toList(),
      total: json['total'] as int,
    );
  }
}
