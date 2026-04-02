// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'loan_status_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

LoanStatusResponse _$LoanStatusResponseFromJson(Map<String, dynamic> json) =>
    LoanStatusResponse(
      loanId: json['loan_id'] as String,
      loanStatus: json['loan_status'] as String,
    );

Map<String, dynamic> _$LoanStatusResponseToJson(LoanStatusResponse instance) =>
    <String, dynamic>{
      'loan_id': instance.loanId,
      'loan_status': instance.loanStatus,
    };
