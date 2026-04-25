// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'loan_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

LoanPublicResponse _$LoanPublicResponseFromJson(Map<String, dynamic> json) =>
    LoanPublicResponse(
      loanId: json['loan_id'] as String,
      assetId: json['asset_id'] as String,
      checkoutLockerId: json['checkout_locker_id'] as String,
      returnLockerId: json['return_locker_id'] as String?,
      reservedAt: json['reserved_at'] == null
          ? null
          : DateTime.parse(json['reserved_at'] as String),
      borrowedAt: json['borrowed_at'] == null
          ? null
          : DateTime.parse(json['borrowed_at'] as String),
      dueDate: json['due_date'] == null
          ? null
          : DateTime.parse(json['due_date'] as String),
      returnedAt: json['returned_at'] == null
          ? null
          : DateTime.parse(json['returned_at'] as String),
      loanStatus: json['loan_status'] as String,
    );

Map<String, dynamic> _$LoanPublicResponseToJson(LoanPublicResponse instance) =>
    <String, dynamic>{
      'loan_id': instance.loanId,
      'asset_id': instance.assetId,
      'checkout_locker_id': instance.checkoutLockerId,
      'return_locker_id': instance.returnLockerId,
      'reserved_at': instance.reservedAt?.toIso8601String(),
      'borrowed_at': instance.borrowedAt?.toIso8601String(),
      'due_date': instance.dueDate?.toIso8601String(),
      'returned_at': instance.returnedAt?.toIso8601String(),
      'loan_status': instance.loanStatus,
    };

LoanResponse _$LoanResponseFromJson(Map<String, dynamic> json) => LoanResponse(
  loanId: json['loan_id'] as String,
  assetId: json['asset_id'] as String,
  checkoutLockerId: json['checkout_locker_id'] as String,
  returnLockerId: json['return_locker_id'] as String?,
  reservedAt: json['reserved_at'] == null
      ? null
      : DateTime.parse(json['reserved_at'] as String),
  borrowedAt: json['borrowed_at'] == null
      ? null
      : DateTime.parse(json['borrowed_at'] as String),
  dueDate: json['due_date'] == null
      ? null
      : DateTime.parse(json['due_date'] as String),
  returnedAt: json['returned_at'] == null
      ? null
      : DateTime.parse(json['returned_at'] as String),
  loanStatus: json['loan_status'] as String,
  userId: json['user_id'] as String,
);

Map<String, dynamic> _$LoanResponseToJson(LoanResponse instance) =>
    <String, dynamic>{
      'loan_id': instance.loanId,
      'asset_id': instance.assetId,
      'checkout_locker_id': instance.checkoutLockerId,
      'return_locker_id': instance.returnLockerId,
      'reserved_at': instance.reservedAt?.toIso8601String(),
      'borrowed_at': instance.borrowedAt?.toIso8601String(),
      'due_date': instance.dueDate?.toIso8601String(),
      'returned_at': instance.returnedAt?.toIso8601String(),
      'loan_status': instance.loanStatus,
      'user_id': instance.userId,
    };
