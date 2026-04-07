import 'package:json_annotation/json_annotation.dart';

part 'error_response.g.dart';

@JsonSerializable()
class ValidationError {
  final List<dynamic> loc;
  final String msg;
  final String type;

  ValidationError({
    required this.loc,
    required this.msg,
    required this.type,
  });

  factory ValidationError.fromJson(Map<String, dynamic> json) =>
      _$ValidationErrorFromJson(json);

  Map<String, dynamic> toJson() => _$ValidationErrorToJson(this);
}

@JsonSerializable()
class ErrorResponse {
  @JsonKey(name: 'detail')
  final List<ValidationError>? detail;

  @JsonKey(name: 'message')
  final String? message;

  ErrorResponse({
    this.detail,
    this.message,
  });

  factory ErrorResponse.fromJson(Map<String, dynamic> json) =>
      _$ErrorResponseFromJson(json);

  Map<String, dynamic> toJson() => _$ErrorResponseToJson(this);

  String get displayMessage {
    if (message != null) return message!;
    if (detail != null && detail!.isNotEmpty) {
      return detail!.map((e) => e.msg).join(', ');
    }
    return 'An error occurred';
  }
}
