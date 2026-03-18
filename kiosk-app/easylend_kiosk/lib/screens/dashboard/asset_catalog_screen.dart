import 'package:flutter/material.dart';
import '../../theme.dart';

class AssetCatalogScreen extends StatelessWidget {
  const AssetCatalogScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        centerTitle: true,
        title: const Text(
          'Asset Catalog',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        actions: [
          TextButton(
            onPressed: () {},
            child: const Text('Logout', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12.0),
              child: TextField(
                style: const TextStyle(color: AppColors.divider),
                decoration: InputDecoration(
                  filled: true,
                  fillColor: AppColors.surface,
                  prefixIcon: Icon(Icons.search, color: AppColors.text),
                  hintText: 'Search assets...',
                  hintStyle: TextStyle(color: AppColors.text),
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
                  _chip('All', selected: true),
                  _chip('In Stock'),
                  _chip('Lent'),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(12, 0, 12, 100),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'My Borrowed Items',
                      style: TextStyle(
                        color: AppColors.divider,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    GridView.count(
                      crossAxisCount: 2,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      crossAxisSpacing: 12,
                      mainAxisSpacing: 12,
                      children: [
                        _borrowedCard(
                          context,
                          'DJI Inspire 3 Drone',
                          'DRN-042',
                          lent: true,
                        ),
                        _borrowedCard(
                          context,
                          'Fluke Analyzer',
                          'TST-088',
                          lent: true,
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Catalog',
                      style: TextStyle(
                        color: AppColors.divider,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    GridView.count(
                      crossAxisCount: 2,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      crossAxisSpacing: 12,
                      mainAxisSpacing: 12,
                      children: [
                        _catalogCard(
                          context,
                          'Sony G-Master Lens',
                          'LNS-001',
                          inStock: true,
                        ),
                        _catalogCard(
                          context,
                          'Leica Total Station',
                          'SRV-103',
                          inStock: true,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: BottomAppBar(
        color: AppColors.background.withAlpha(242),
        child: SizedBox(
          height: 72,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _navItem(Icons.grid_view, 'Catalog', selected: true),
              _navItem(Icons.sync_alt, 'Transfers'),
              FloatingActionButton(
                onPressed: () {},
                child: const Icon(Icons.qr_code_scanner),
              ),
              _navItem(Icons.history, 'History'),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chip(String label, {bool selected = false}) => Container(
    margin: const EdgeInsets.only(right: 8),
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
    decoration: BoxDecoration(
      color: selected ? Colors.blue : const Color(0xFF111111),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      label,
      style: TextStyle(color: selected ? Colors.white : Colors.grey),
    ),
  );

  Widget _borrowedCard(
    BuildContext context,
    String title,
    String id, {
    bool lent = false,
  }) => Container(
    decoration: BoxDecoration(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: AppColors.surface),
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
          ),
        ),
        const SizedBox(height: 8),
        Text(
          title,
          style: const TextStyle(
            color: AppColors.divider,
            fontWeight: FontWeight.bold,
          ),
        ),
        Text(
          'ID: $id',
          style: const TextStyle(color: AppColors.text, fontSize: 12),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                color: lent ? AppColors.accent : AppColors.surface,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 6),
            Text(
              lent ? 'Lent' : 'In Stock',
              style: TextStyle(
                color: lent
                    ? AppColors.accent.withAlpha(204)
                    : AppColors.surface.withAlpha(204),
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
              backgroundColor: Colors.grey.shade800,
              foregroundColor: Colors.white,
            ),
            onPressed: () {},
            child: Text(lent ? 'Return' : 'Lend'),
          ),
        ),
      ],
    ),
  );

  Widget _catalogCard(
    BuildContext context,
    String title,
    String id, {
    bool inStock = false,
  }) => Container(
    decoration: BoxDecoration(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: AppColors.surface),
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
          ),
        ),
        const SizedBox(height: 8),
        Text(
          title,
          style: const TextStyle(
            color: AppColors.divider,
            fontWeight: FontWeight.bold,
          ),
        ),
        Text(
          'ID: $id',
          style: const TextStyle(color: AppColors.text, fontSize: 12),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                color: inStock ? AppColors.surface : AppColors.accent,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 6),
            Text(
              inStock ? 'In Stock' : 'Lent',
              style: TextStyle(
                color: inStock
                    ? AppColors.surface.withAlpha(179)
                    : AppColors.accent.withAlpha(179),
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
              backgroundColor: inStock
                  ? AppColors.primary
                  : Colors.grey.shade800,
              foregroundColor: AppColors.divider,
            ),
            onPressed: () {},
            child: Text(inStock ? 'Lend' : 'Return'),
          ),
        ),
      ],
    ),
  );

  Widget _navItem(IconData icon, String label, {bool selected = false}) =>
      Column(
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
