// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'pin_login_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

PinLoginRequest _$PinLoginRequestFromJson(Map<String, dynamic> json) =>
    PinLoginRequest(
      nfcTagId: json['nfc_tag_id'] as String,
      pin: json['pin'] as String,
    );

Map<String, dynamic> _$PinLoginRequestToJson(PinLoginRequest instance) =>
    <String, dynamic>{'nfc_tag_id': instance.nfcTagId, 'pin': instance.pin};
