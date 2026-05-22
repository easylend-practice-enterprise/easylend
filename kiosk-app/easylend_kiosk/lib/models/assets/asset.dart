import 'package:json_annotation/json_annotation.dart';

part 'asset.g.dart';

@JsonSerializable()
class Asset {
  @JsonKey(name: 'asset_id')
  final String assetId;

  final String name;

  @JsonKey(name: 'aztec_code')
  final String aztecCode;

  @JsonKey(name: 'asset_status')
  final String assetStatus;

  @JsonKey(name: 'category_id')
  final String categoryId;

  @JsonKey(name: 'locker_id')
  final String? lockerId;

  @JsonKey(name: 'is_deleted')
  final bool isDeleted;

  Asset({
    required this.assetId,
    required this.name,
    required this.aztecCode,
    required this.assetStatus,
    required this.categoryId,
    this.lockerId,
    required this.isDeleted,
  });

  factory Asset.fromJson(Map<String, dynamic> json) => _$AssetFromJson(json);

  Map<String, dynamic> toJson() => _$AssetToJson(this);
}