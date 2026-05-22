// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'asset.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

Asset _$AssetFromJson(Map<String, dynamic> json) => Asset(
  assetId: json['asset_id'] as String,
  name: json['name'] as String,
  aztecCode: json['aztec_code'] as String,
  assetStatus: json['asset_status'] as String,
  categoryId: json['category_id'] as String,
  lockerId: json['locker_id'] as String?,
  isDeleted: json['is_deleted'] as bool,
);

Map<String, dynamic> _$AssetToJson(Asset instance) => <String, dynamic>{
  'asset_id': instance.assetId,
  'name': instance.name,
  'aztec_code': instance.aztecCode,
  'asset_status': instance.assetStatus,
  'category_id': instance.categoryId,
  'locker_id': instance.lockerId,
  'is_deleted': instance.isDeleted,
};
