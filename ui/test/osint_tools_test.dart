import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/osint/osint_tools.dart';

void main() {
  group('JarvisOsint input validation', () {
    test('rejects malformed email before network access', () async {
      await expectLater(JarvisOsint.lookup('Email', 'not-an-email'), throwsArgumentError);
    });
    test('rejects invalid username before network access', () async {
      await expectLater(JarvisOsint.lookup('Username', 'bad name!'), throwsArgumentError);
    });
    test('rejects invalid IP address before network access', () async {
      await expectLater(JarvisOsint.lookup('IP / ASN', 'not-an-ip'), throwsArgumentError);
    });
    test('rejects non-HTTPS image URL', () async {
      await expectLater(JarvisOsint.lookup('Image URL / EXIF', 'http://example.com/image.jpg'), throwsArgumentError);
    });
  });
}
