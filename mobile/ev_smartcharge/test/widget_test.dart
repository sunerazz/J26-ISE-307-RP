import 'package:ev_smartcharge/format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('missing measurements stay labelled unavailable', () {
    expect(fmtKm(null), 'Unavailable');
    expect(fmtMinutes(null), 'Unavailable');
    expect(fmtLkr(null), 'Unavailable');
    expect(fmtKm(3.24), '3.2 km');
    expect(fmtLkr(980), 'Rs. 980');
  });
}
