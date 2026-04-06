import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/debug_credentials.dart';
import '../../models/catalog/catalog_item.dart';
import '../../providers/providers.dart';
import '../../theme.dart';

enum CatalogFilter { all, inStock, lent }

class AssetCatalogScreen extends ConsumerStatefulWidget {
  const AssetCatalogScreen({super.key});

  @override
  ConsumerState<AssetCatalogScreen> createState() => _AssetCatalogScreenState();
}

class _AssetCatalogScreenState extends ConsumerState<AssetCatalogScreen> {
  final TextEditingController _searchController = TextEditingController();
  CatalogFilter _selectedFilter = CatalogFilter.all;
  String _searchQuery = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _onFilterChanged(CatalogFilter filter) {
    setState(() => _selectedFilter = filter);
  }

  void _onSearchChanged(String query) {
    setState(() => _searchQuery = query);
  }

  Future<void> _onLogout() async {
    await ref.read(authProvider.notifier).logout();
    if (mounted) {
      context.go('/login');
    }
  }

  void _onLendItem(CatalogUserView item) {
    // Navigate to scan screen for checkout
    context.go('/scan');
  }

  void _onRefresh() {
    ref.invalidate(catalogProvider);
  }

  @override
  Widget build(BuildContext context) {
    final catalogAsync = ref.watch(catalogProvider);
    final authState = ref.watch(authProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        centerTitle: true,
        title: Text(
          'Welcome, ${authState.user?.firstName ?? 'User'}',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        actions: [
          TextButton(
            onPressed: _onLogout,
            child: Text('Logout', style: TextStyle(color: AppColors.accent)),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12.0),
              child: TextField(
                controller: _searchController,
                onChanged: _onSearchChanged,
                style: TextStyle(color: AppColors.text),
                decoration: InputDecoration(
                  filled: true,
                  fillColor: AppColors.surface,
                  prefixIcon: Icon(Icons.search, color: AppColors.text),
                  hintText: 'Search assets...',
                  hintStyle: TextStyle(color: AppColors.text.withAlpha(128)),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
            SizedBox(
              height: 52,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  _FilterChip(
                    label: 'All',
                    selected: _selectedFilter == CatalogFilter.all,
                    onSelected: () => _onFilterChanged(CatalogFilter.all),
                  ),
                  _FilterChip(
                    label: 'In Stock',
                    selected: _selectedFilter == CatalogFilter.inStock,
                    onSelected: () => _onFilterChanged(CatalogFilter.inStock),
                  ),
                  _FilterChip(
                    label: 'Lent',
                    selected: _selectedFilter == CatalogFilter.lent,
                    onSelected: () => _onFilterChanged(CatalogFilter.lent),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: catalogAsync.when(
                data: (items) {
                  if (items.isEmpty) {
                    return _buildEmptyState();
                  }
                  return _buildCatalogList(items);
                },
                loading: () => const Center(
                  child: CircularProgressIndicator(),
                ),
                error: (error, _) => _buildErrorState(error.toString()),
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: BottomAppBar(
        color: AppColors.surface,
        child: SizedBox(
          height: 72,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              if (!DebugConfig.isActive) ...[
                _NavItem(icon: Icons.grid_view, label: 'Catalog', selected: true),
                _NavItem(icon: Icons.sync_alt, label: 'Transfers', selected: false),
              ],
              FloatingActionButton(
                onPressed: () => context.go('/scan'),
                child: const Icon(Icons.qr_code_scanner),
              ),
              if (!DebugConfig.isActive)
                _NavItem(icon: Icons.history, label: 'History', selected: false),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.inventory_2_outlined, size: 64, color: AppColors.text.withAlpha(128)),
          const SizedBox(height: 16),
          Text(
            'No items available',
            style: TextStyle(color: AppColors.text, fontSize: 18),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: _onRefresh,
            child: const Text('Refresh'),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState(String error) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 64, color: Colors.red.withAlpha(200)),
            const SizedBox(height: 16),
            Text(
              'Failed to load catalog',
              style: TextStyle(color: AppColors.text, fontSize: 18),
            ),
            const SizedBox(height: 8),
            Text(
              error,
              style: TextStyle(color: AppColors.text.withAlpha(180), fontSize: 14),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _onRefresh,
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCatalogList(List<CatalogUserView> items) {
    final userItems = items;
    final adminItems = items.whereType<CatalogAdminView>().toList();

    // If admin view items exist, show them
    if (adminItems.isNotEmpty) {
      return _buildAdminCatalogList(adminItems);
    }

    // Otherwise show user view
    return _buildUserCatalogList(userItems);
  }

  Widget _buildUserCatalogList(List<CatalogUserView> items) {
    final filtered = items.where((item) {
      final matchesSearch = _searchQuery.isEmpty ||
          item.categoryName.toLowerCase().contains(_searchQuery.toLowerCase());
      final matchesFilter = _selectedFilter == CatalogFilter.all ||
          (_selectedFilter == CatalogFilter.inStock && item.availableCount > 0) ||
          (_selectedFilter == CatalogFilter.lent && item.availableCount == 0);
      return matchesSearch && matchesFilter;
    }).toList();

    if (filtered.isEmpty) {
      return _buildEmptyState();
    }

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(catalogProvider),
      child: GridView.builder(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 100),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          childAspectRatio: 0.85,
        ),
        itemCount: filtered.length,
        itemBuilder: (context, index) {
          final item = filtered[index];
          return _CatalogCard(
            item: item,
            onTap: item.availableCount > 0 ? () => _onLendItem(item) : null,
          );
        },
      ),
    );
  }

  Widget _buildAdminCatalogList(List<CatalogAdminView> items) {
    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(catalogProvider),
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 100),
        itemCount: items.length,
        itemBuilder: (context, index) {
          final item = items[index];
          return _AdminAssetTile(item: item);
        },
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onSelected;

  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onSelected,
      child: Container(
        margin: const EdgeInsets.only(right: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: selected ? AppColors.primary : const Color(0xFF111111),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? AppColors.onPrimary : AppColors.text,
          ),
        ),
      ),
    );
  }
}

class _CatalogCard extends StatelessWidget {
  final CatalogUserView item;
  final VoidCallback? onTap;

  const _CatalogCard({required this.item, this.onTap});

  @override
  Widget build(BuildContext context) {
    final inStock = item.availableCount > 0;

    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Icon(
                  Icons.inventory_2,
                  size: 48,
                  color: AppColors.text.withAlpha(128),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            item.categoryName,
            style: TextStyle(
              color: AppColors.text,
              fontWeight: FontWeight.bold,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: inStock ? AppColors.accent : AppColors.text.withAlpha(128),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                '${item.availableCount} available',
                style: TextStyle(
                  color: inStock ? AppColors.accent : AppColors.text.withAlpha(128),
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: TextButton(
              style: TextButton.styleFrom(
                backgroundColor: inStock ? AppColors.primary : AppColors.surface,
                foregroundColor: AppColors.text,
              ),
              onPressed: onTap,
              child: Text(inStock ? 'Lend' : 'Unavailable'),
            ),
          ),
        ],
      ),
    );
  }
}

class _AdminAssetTile extends StatelessWidget {
  final CatalogAdminView item;

  const _AdminAssetTile({required this.item});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: AppColors.background,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              Icons.inventory_2,
              color: AppColors.text.withAlpha(128),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.assetName,
                  style: TextStyle(
                    color: AppColors.text,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  'Status: ${item.assetStatus}',
                  style: TextStyle(
                    color: AppColors.text.withAlpha(180),
                    fontSize: 12,
                  ),
                ),
                if (item.loanStatus != null)
                  Text(
                    'Loan: ${item.loanStatus}',
                    style: TextStyle(
                      color: AppColors.text.withAlpha(180),
                      fontSize: 12,
                    ),
                  ),
              ],
            ),
          ),
          Icon(
            item.isDeleted ? Icons.delete : Icons.check_circle,
            color: item.isDeleted ? Colors.red : Colors.green,
          ),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool selected;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.selected,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: selected ? AppColors.primary : AppColors.text),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            color: selected ? AppColors.primary : AppColors.text,
            fontSize: 10,
          ),
        ),
      ],
    );
  }
}
