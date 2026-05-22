// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'asset_list_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AssetListResponse _$AssetListResponseFromJson(Map<String, dynamic> json) =>
    AssetListResponse(
      items: (json['items'] as List<dynamic>)
          .map((e) => Asset.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: (json['total'] as num).toInt(),
    );

Map<String, dynamic> _$AssetListResponseToJson(AssetListResponse instance) =>
    <String, dynamic>{'items': instance.items, 'total': instance.total};
