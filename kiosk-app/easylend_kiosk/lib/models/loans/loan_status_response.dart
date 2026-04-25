import 'package:json_annotation/json_annotation.dart';

part 'loan_status_response.g.dart';

@JsonSerializable()
class LoanStatusResponse {
  @JsonKey(name: 'loan_id')
  final String loanId;

  @JsonKey(name: 'loan_status')
  final String loanStatus;

  LoanStatusResponse({
    required this.loanId,
    required this.loanStatus,
  });

  factory LoanStatusResponse.fromJson(Map<String, dynamic> json) =>
      _$LoanStatusResponseFromJson(json);

  Map<String, dynamic> toJson() => _$LoanStatusResponseToJson(this);
}
