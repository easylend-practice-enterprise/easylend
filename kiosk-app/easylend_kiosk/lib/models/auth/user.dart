import 'package:json_annotation/json_annotation.dart';

part 'user.g.dart';

@JsonSerializable()
class User {
  @JsonKey(name: 'user_id')
  final String userId;

  @JsonKey(name: 'role_id')
  final String roleId;

  @JsonKey(name: 'role_name')
  final String roleName;

  @JsonKey(name: 'first_name')
  final String firstName;

  @JsonKey(name: 'last_name')
  final String lastName;

  @JsonKey(name: 'email')
  final String email;

  @JsonKey(name: 'nfc_tag_id')
  final String? nfcTagId;

  @JsonKey(name: 'failed_login_attempts')
  final int failedLoginAttempts;

  @JsonKey(name: 'locked_until')
  final DateTime? lockedUntil;

  @JsonKey(name: 'is_active')
  final bool isActive;

  @JsonKey(name: 'is_anonymized')
  final bool isAnonymized;

  @JsonKey(name: 'ban_reason')
  final String? banReason;

  @JsonKey(name: 'accepted_privacy_policy')
  final bool acceptedPrivacyPolicy;

  User({
    required this.userId,
    required this.roleId,
    required this.roleName,
    required this.firstName,
    required this.lastName,
    required this.email,
    this.nfcTagId,
    required this.failedLoginAttempts,
    this.lockedUntil,
    required this.isActive,
    required this.isAnonymized,
    this.banReason,
    required this.acceptedPrivacyPolicy,
  });

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);

  Map<String, dynamic> toJson() => _$UserToJson(this);

  bool get isAdmin => roleName.toUpperCase() == 'ADMIN';
}
