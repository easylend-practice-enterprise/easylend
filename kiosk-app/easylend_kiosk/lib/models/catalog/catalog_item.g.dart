// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'catalog_item.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

CatalogUserView _$CatalogUserViewFromJson(Map<String, dynamic> json) =>
    CatalogUserView(
      categoryId: json['category_id'] as String,
      categoryName: json['category_name'] as String,
      availableCount: (json['available_count'] as num).toInt(),
    );

Map<String, dynamic> _$CatalogUserViewToJson(CatalogUserView instance) =>
    <String, dynamic>{
      'category_id': instance.categoryId,
      'category_name': instance.categoryName,
      'available_count': instance.availableCount,
    };

CatalogAdminView _$CatalogAdminViewFromJson(Map<String, dynamic> json) =>
    CatalogAdminView(
      assetId: json['asset_id'] as String,
      assetName: json['asset_name'] as String,
      categoryId: json['category_id'] as String,
      assetStatus: json['asset_status'] as String,
      lockerId: json['locker_id'] as String?,
      isDeleted: json['is_deleted'] as bool,
      loanStatus: json['loan_status'] as String?,
      borrowerFirstName: json['borrower_first_name'] as String?,
      borrowerLastName: json['borrower_last_name'] as String?,
    );

Map<String, dynamic> _$CatalogAdminViewToJson(CatalogAdminView instance) =>
    <String, dynamic>{
      'asset_id': instance.assetId,
      'asset_name': instance.assetName,
      'category_id': instance.categoryId,
      'asset_status': instance.assetStatus,
      'locker_id': instance.lockerId,
      'is_deleted': instance.isDeleted,
      'loan_status': instance.loanStatus,
      'borrower_first_name': instance.borrowerFirstName,
      'borrower_last_name': instance.borrowerLastName,
    };
