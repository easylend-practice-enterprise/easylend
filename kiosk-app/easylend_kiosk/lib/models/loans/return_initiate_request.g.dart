// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'return_initiate_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ReturnInitiateRequest _$ReturnInitiateRequestFromJson(
  Map<String, dynamic> json,
) => ReturnInitiateRequest(
  loanId: json['loan_id'] as String,
  kioskId: json['kiosk_id'] as String,
);

Map<String, dynamic> _$ReturnInitiateRequestToJson(
  ReturnInitiateRequest instance,
) => <String, dynamic>{
  'loan_id': instance.loanId,
  'kiosk_id': instance.kioskId,
};
