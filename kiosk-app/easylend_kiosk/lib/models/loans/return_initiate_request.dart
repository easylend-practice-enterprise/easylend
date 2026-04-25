import 'package:json_annotation/json_annotation.dart';

part 'return_initiate_request.g.dart';

@JsonSerializable()
class ReturnInitiateRequest {
  @JsonKey(name: 'loan_id')
  final String loanId;

  @JsonKey(name: 'kiosk_id')
  final String kioskId;

  ReturnInitiateRequest({
    required this.loanId,
    required this.kioskId,
  });

  factory ReturnInitiateRequest.fromJson(Map<String, dynamic> json) =>
      _$ReturnInitiateRequestFromJson(json);

  Map<String, dynamic> toJson() => _$ReturnInitiateRequestToJson(this);
}
