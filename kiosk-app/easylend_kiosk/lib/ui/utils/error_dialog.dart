import 'package:flutter/material.dart';

import '../../theme.dart';

Future<void> showErrorDialog(
  BuildContext context,
  String title,
  String message,
) async {
  await showDialog(
    context: context,
    builder: (context) => AlertDialog(
      backgroundColor: AppColors.surface,
      title: Text(
        title,
        style: TextStyle(color: AppColors.text, fontSize: 24, fontWeight: FontWeight.bold),
      ),
      content: Text(
        message,
        style: TextStyle(color: AppColors.text.withAlpha(204), fontSize: 18),
      ),
      actions: [
        TextButton(
          onPressed: () {
            if (!context.mounted) return;
            Navigator.of(context).pop();
          },
          child: Text(
            'Sluiten',
            style: TextStyle(color: AppColors.accent, fontSize: 18),
          ),
        ),
      ],
    ),
  );
}