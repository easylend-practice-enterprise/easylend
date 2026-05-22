import 'package:json_annotation/json_annotation.dart';
import '../assets/asset.dart';

part 'asset_list_response.g.dart';

@JsonSerializable()
class AssetListResponse {
  final List<Asset> items;
  final int total;

  AssetListResponse({
    required this.items,
    required this.total,
  });

  factory AssetListResponse.fromJson(Map<String, dynamic> json) =>
      _$AssetListResponseFromJson(json);

  Map<String, dynamic> toJson() => _$AssetListResponseToJson(this);
}