// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'return_initiate_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ReturnInitiateRequest _$ReturnInitiateRequestFromJson(
  Map<String, dynamic> json,
) => ReturnInitiateRequest(
  aztecCode: json['aztec_code'] as String,
  kioskId: json['kiosk_id'] as String,
);

Map<String, dynamic> _$ReturnInitiateRequestToJson(
  ReturnInitiateRequest instance,
) => <String, dynamic>{
  'aztec_code': instance.aztecCode,
  'kiosk_id': instance.kioskId,
};
