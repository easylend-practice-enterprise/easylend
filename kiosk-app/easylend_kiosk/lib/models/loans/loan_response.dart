import 'package:json_annotation/json_annotation.dart';

part 'loan_response.g.dart';

/// Loan status values from the API
class LoanStatus {
  static const String reserved = 'RESERVED';
  static const String active = 'ACTIVE';
  static const String returning = 'RETURNING';
  static const String overdue = 'OVERDUE';
  static const String completed = 'COMPLETED';
  static const String fraudSuspected = 'FRAUD_SUSPECTED';
  static const String disputed = 'DISPUTED';
  static const String pendingInspection = 'PENDING_INSPECTION';
}

/// Public loan response (non-admin) - no user_id
@JsonSerializable()
class LoanPublicResponse {
  @JsonKey(name: 'loan_id')
  final String loanId;

  @JsonKey(name: 'asset_id')
  final String assetId;

  @JsonKey(name: 'checkout_locker_id')
  final String checkoutLockerId;

  @JsonKey(name: 'return_locker_id')
  final String? returnLockerId;

  @JsonKey(name: 'reserved_at')
  final DateTime? reservedAt;

  @JsonKey(name: 'borrowed_at')
  final DateTime? borrowedAt;

  @JsonKey(name: 'due_date')
  final DateTime? dueDate;

  @JsonKey(name: 'returned_at')
  final DateTime? returnedAt;

  @JsonKey(name: 'loan_status')
  final String loanStatus;

  LoanPublicResponse({
    required this.loanId,
    required this.assetId,
    required this.checkoutLockerId,
    this.returnLockerId,
    this.reservedAt,
    this.borrowedAt,
    this.dueDate,
    this.returnedAt,
    required this.loanStatus,
  });

  factory LoanPublicResponse.fromJson(Map<String, dynamic> json) =>
      _$LoanPublicResponseFromJson(json);

  Map<String, dynamic> toJson() => _$LoanPublicResponseToJson(this);

  bool get isActive => loanStatus == LoanStatus.active;
  bool get isCompleted => loanStatus == LoanStatus.completed;
  bool get isReserved => loanStatus == LoanStatus.reserved;
  bool get isReturning => loanStatus == LoanStatus.returning;
  bool get isPendingInspection => loanStatus == LoanStatus.pendingInspection;
}

/// Admin loan response - includes user_id
@JsonSerializable()
class LoanResponse {
  @JsonKey(name: 'loan_id')
  final String loanId;

  @JsonKey(name: 'asset_id')
  final String assetId;

  @JsonKey(name: 'checkout_locker_id')
  final String checkoutLockerId;

  @JsonKey(name: 'return_locker_id')
  final String? returnLockerId;

  @JsonKey(name: 'reserved_at')
  final DateTime? reservedAt;

  @JsonKey(name: 'borrowed_at')
  final DateTime? borrowedAt;

  @JsonKey(name: 'due_date')
  final DateTime? dueDate;

  @JsonKey(name: 'returned_at')
  final DateTime? returnedAt;

  @JsonKey(name: 'loan_status')
  final String loanStatus;

  @JsonKey(name: 'user_id')
  final String userId;

  LoanResponse({
    required this.loanId,
    required this.assetId,
    required this.checkoutLockerId,
    this.returnLockerId,
    this.reservedAt,
    this.borrowedAt,
    this.dueDate,
    this.returnedAt,
    required this.loanStatus,
    required this.userId,
  });

  factory LoanResponse.fromJson(Map<String, dynamic> json) =>
      _$LoanResponseFromJson(json);

  Map<String, dynamic> toJson() => _$LoanResponseToJson(this);
}
