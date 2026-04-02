import 'package:json_annotation/json_annotation.dart';

part 'nfc_login_request.g.dart';

@JsonSerializable()
class NfcLoginRequest {
  @JsonKey(name: 'nfc_tag_id')
  final String nfcTagId;

  NfcLoginRequest({required this.nfcTagId});

  factory NfcLoginRequest.fromJson(Map<String, dynamic> json) =>
      _$NfcLoginRequestFromJson(json);

  Map<String, dynamic> toJson() => _$NfcLoginRequestToJson(this);
}
