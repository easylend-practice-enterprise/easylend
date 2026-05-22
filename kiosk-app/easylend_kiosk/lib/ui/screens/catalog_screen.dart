import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/assets/asset.dart';
import '../../services/api/kiosk_api_service.dart';
import '../../theme.dart';

class CatalogScreen extends ConsumerStatefulWidget {
  const CatalogScreen({super.key});

  @override
  ConsumerState<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends ConsumerState<CatalogScreen>
    with AutomaticKeepAliveClientMixin {
  final KioskApiService _apiService = KioskApiService();
  List<Asset> _availableAssets = [];
  bool _isLoading = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _fetchAssets();
  }

  Future<void> _fetchAssets() async {
    final assets = await _apiService.fetchAvailableAssets();
    if (mounted) {
      setState(() {
        _availableAssets = assets;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('EasyLend Catalog'),
        backgroundColor: AppColors.background,
        elevation: 0,
        centerTitle: true,
      ),
      backgroundColor: AppColors.background,
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_availableAssets.isEmpty) {
      return Center(
        child: Text(
          'No assets available.',
          style: TextStyle(color: AppColors.text, fontSize: 20),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _fetchAssets,
      child: GridView.builder(
        padding: const EdgeInsets.all(20),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          crossAxisSpacing: 20,
          mainAxisSpacing: 20,
          childAspectRatio: 0.75,
        ),
        itemCount: _availableAssets.length,
        itemBuilder: (context, index) {
          final asset = _availableAssets[index];
          return _AssetCard(asset: asset);
        },
      ),
    );
  }
}

class _AssetCard extends StatelessWidget {
  final Asset asset;

  const _AssetCard({required this.asset});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Icon(
                  Icons.inventory_2,
                  size: 72,
                  color: AppColors.text.withAlpha(128),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            asset.name,
            style: TextStyle(
              color: AppColors.text,
              fontWeight: FontWeight.bold,
              fontSize: 24,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 6),
          Text(
            asset.assetStatus,
            style: TextStyle(
              color: AppColors.accent,
              fontWeight: FontWeight.w600,
              fontSize: 20,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            asset.aztecCode,
            style: TextStyle(
              color: AppColors.text.withAlpha(153),
              fontSize: 16,
            ),
          ),
        ],
      ),
    );
  }
}