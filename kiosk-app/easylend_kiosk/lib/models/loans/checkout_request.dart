import 'package:json_annotation/json_annotation.dart';

part 'checkout_request.g.dart';

@JsonSerializable()
class CheckoutRequest {
  @JsonKey(name: 'aztec_code')
  final String aztecCode;

  CheckoutRequest({required this.aztecCode});

  factory CheckoutRequest.fromJson(Map<String, dynamic> json) =>
      _$CheckoutRequestFromJson(json);

  Map<String, dynamic> toJson() => _$CheckoutRequestToJson(this);
}
