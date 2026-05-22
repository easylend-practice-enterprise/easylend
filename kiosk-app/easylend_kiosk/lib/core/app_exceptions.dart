/// Base application exception with user-facing message.
class AppException implements Exception {
  final String message;
  final int? code;

  const AppException(this.message, {this.code});

  @override
  String toString() => message;

  factory AppException.networkError() => const AppException(
        'No internet connection. Please check the network.',
      );

  factory AppException.serverError() => const AppException(
        'Server error. Please try again later.',
        code: 500,
      );

  factory AppException.clientError(int statusCode) => AppException(
        _clientErrorMessage(statusCode),
        code: statusCode,
      );

  static String _clientErrorMessage(int code) {
    switch (code) {
      case 400:
        return 'Invalid request. Please check your input.';
      case 404:
        return 'Resource not found.';
      case 409:
        return 'Conflict or resource already in use.';
      default:
        return 'Request failed. Please try again.';
    }
  }
}