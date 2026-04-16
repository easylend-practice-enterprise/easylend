// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'user.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

User _$UserFromJson(Map<String, dynamic> json) => User(
  userId: json['user_id'] as String,
  roleId: json['role_id'] as String,
  roleName: json['role_name'] as String,
  firstName: json['first_name'] as String,
  lastName: json['last_name'] as String,
  email: json['email'] as String,
  nfcTagId: json['nfc_tag_id'] as String?,
  failedLoginAttempts: (json['failed_login_attempts'] as num).toInt(),
  lockedUntil: json['locked_until'] == null
      ? null
      : DateTime.parse(json['locked_until'] as String),
  isActive: json['is_active'] as bool,
  isAnonymized: json['is_anonymized'] as bool,
  banReason: json['ban_reason'] as String?,
  acceptedPrivacyPolicy: json['accepted_privacy_policy'] as bool,
);

Map<String, dynamic> _$UserToJson(User instance) => <String, dynamic>{
  'user_id': instance.userId,
  'role_id': instance.roleId,
  'role_name': instance.roleName,
  'first_name': instance.firstName,
  'last_name': instance.lastName,
  'email': instance.email,
  'nfc_tag_id': instance.nfcTagId,
  'failed_login_attempts': instance.failedLoginAttempts,
  'locked_until': instance.lockedUntil?.toIso8601String(),
  'is_active': instance.isActive,
  'is_anonymized': instance.isAnonymized,
  'ban_reason': instance.banReason,
  'accepted_privacy_policy': instance.acceptedPrivacyPolicy,
};
