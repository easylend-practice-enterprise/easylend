import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/providers.dart';
import '../../theme.dart';
import '../../models/loans/loan_response.dart';

class ReturnStatusScreen extends ConsumerStatefulWidget {
  final String loanId;

  const ReturnStatusScreen({super.key, required this.loanId});

  @override
  ConsumerState<ReturnStatusScreen> createState() => _ReturnStatusScreenState();
}

class _ReturnStatusScreenState extends ConsumerState<ReturnStatusScreen> {
  @override
  void initState() {
    super.initState();
    // Start polling when the screen loads
    Future.microtask(() {
      ref.read(loanPollingProvider(widget.loanId).notifier).startPolling();
    });
  }

  @override
  void dispose() {
    ref.read(loanPollingProvider(widget.loanId).notifier).stopPolling();
    super.dispose();
  }

  String _getStatusMessage(String? status) {
    switch (status) {
      case LoanStatus.reserved:
        return 'Reserving your item...';
      case LoanStatus.active:
        return 'Item picked up successfully!';
      case LoanStatus.returning:
        return 'Processing your return...';
      case LoanStatus.overdue:
        return 'Item is overdue!';
      case LoanStatus.completed:
        return 'Return Complete!';
      case LoanStatus.pendingInspection:
        return 'Inspection Required';
      case LoanStatus.fraudSuspected:
        return 'Issue Detected';
      case LoanStatus.disputed:
        return 'Return Disputed';
      default:
        return 'Processing...';
    }
  }

  IconData _getStatusIcon(String? status) {
    switch (status) {
      case LoanStatus.completed:
        return Icons.check_circle;
      case LoanStatus.pendingInspection:
      case LoanStatus.fraudSuspected:
      case LoanStatus.disputed:
        return Icons.warning;
      default:
        return Icons.hourglass_empty;
    }
  }

  Color _getStatusColor(String? status) {
    switch (status) {
      case LoanStatus.completed:
        return Colors.green;
      case LoanStatus.pendingInspection:
      case LoanStatus.overdue:
        return Colors.orange;
      case LoanStatus.fraudSuspected:
      case LoanStatus.disputed:
        return Colors.red;
      default:
        return AppColors.primary;
    }
  }

  @override
  Widget build(BuildContext context) {
    final pollingState = ref.watch(loanPollingProvider(widget.loanId));

    // Calculate progress based on status
    double progress = 0.0;
    if (pollingState.currentStatus != null) {
      switch (pollingState.currentStatus) {
        case LoanStatus.reserved:
          progress = 0.25;
          break;
        case LoanStatus.active:
          progress = 0.5;
          break;
        case LoanStatus.returning:
          progress = 0.75;
          break;
        case LoanStatus.completed:
        case LoanStatus.pendingInspection:
        case LoanStatus.fraudSuspected:
        case LoanStatus.disputed:
          progress = 1.0;
          break;
        default:
          progress = 0.1;
      }
    }

    final isComplete = pollingState.isComplete || progress == 1.0;
    final statusColor = _getStatusColor(pollingState.currentStatus);
    final statusIcon = _getStatusIcon(pollingState.currentStatus);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => context.go('/catalog'),
        ),
        title: const Text(
          'Return Status',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox(
                    width: 120,
                    height: 120,
                    child: CircularProgressIndicator(
                      value: progress,
                      strokeWidth: 6,
                      color: statusColor,
                    ),
                  ),
                  if (isComplete)
                    Icon(
                      statusIcon,
                      size: 48,
                      color: statusColor,
                    )
                  else
                    Text(
                      '${(progress * 100).toInt()}%',
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 24),
              Text(
                _getStatusMessage(pollingState.currentStatus),
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                pollingState.hasError
                    ? 'Error: ${pollingState.error}'
                    : 'Please place the item in the vision box.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: pollingState.hasError ? Colors.red : AppColors.text,
                ),
              ),
              if (isComplete) ...[
                const SizedBox(height: 32),
                ElevatedButton(
                  onPressed: () => context.go('/catalog'),
                  child: const Text('Done'),
                ),
              ],
              if (pollingState.hasError) ...[
                const SizedBox(height: 32),
                ElevatedButton(
                  onPressed: () {
                    ref.read(loanPollingProvider(widget.loanId).notifier).startPolling();
                  },
                  child: const Text('Retry'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
