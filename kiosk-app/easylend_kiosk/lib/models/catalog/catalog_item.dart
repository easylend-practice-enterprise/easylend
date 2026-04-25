import 'package:json_annotation/json_annotation.dart';

part 'catalog_item.g.dart';

/// User view - grouped category counts for non-admin users
@JsonSerializable()
class CatalogUserView {
  @JsonKey(name: 'category_id')
  final String categoryId;

  @JsonKey(name: 'category_name')
  final String categoryName;

  @JsonKey(name: 'available_count')
  final int availableCount;

  CatalogUserView({
    required this.categoryId,
    required this.categoryName,
    required this.availableCount,
  });

  factory CatalogUserView.fromJson(Map<String, dynamic> json) =>
      _$CatalogUserViewFromJson(json);

  Map<String, dynamic> toJson() => _$CatalogUserViewToJson(this);
}

/// Admin view - one row per asset with loan context
@JsonSerializable()
class CatalogAdminView {
  @JsonKey(name: 'asset_id')
  final String assetId;

  @JsonKey(name: 'asset_name')
  final String assetName;

  @JsonKey(name: 'category_id')
  final String categoryId;

  @JsonKey(name: 'asset_status')
  final String assetStatus;

  @JsonKey(name: 'locker_id')
  final String? lockerId;

  @JsonKey(name: 'is_deleted')
  final bool isDeleted;

  @JsonKey(name: 'loan_status')
  final String? loanStatus;

  @JsonKey(name: 'borrower_first_name')
  final String? borrowerFirstName;

  @JsonKey(name: 'borrower_last_name')
  final String? borrowerLastName;

  CatalogAdminView({
    required this.assetId,
    required this.assetName,
    required this.categoryId,
    required this.assetStatus,
    this.lockerId,
    required this.isDeleted,
    this.loanStatus,
    this.borrowerFirstName,
    this.borrowerLastName,
  });

  factory CatalogAdminView.fromJson(Map<String, dynamic> json) =>
      _$CatalogAdminViewFromJson(json);

  Map<String, dynamic> toJson() => _$CatalogAdminViewToJson(this);
}
