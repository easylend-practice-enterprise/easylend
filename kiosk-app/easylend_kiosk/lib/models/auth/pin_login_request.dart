import 'package:json_annotation/json_annotation.dart';

part 'pin_login_request.g.dart';

@JsonSerializable()
class PinLoginRequest {
  @JsonKey(name: 'nfc_tag_id')
  final String nfcTagId;

  @JsonKey(name: 'pin')
  final String pin;

  PinLoginRequest({required this.nfcTagId, required this.pin});

  factory PinLoginRequest.fromJson(Map<String, dynamic> json) =>
      _$PinLoginRequestFromJson(json);

  Map<String, dynamic> toJson() => _$PinLoginRequestToJson(this);
}
