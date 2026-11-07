import socket
import unittest
from unittest import mock

from agent.tools import osint


def addr(ip, port):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (ip, port))


class TestOsintUrlSafety(unittest.TestCase):
    def test_rejects_loopback_literal(self):
        with self.assertRaisesRegex(ValueError, "непубличный IP"):
            osint._validate_public_http_url("http://127.0.0.1/admin")

    def test_rejects_private_dns_resolution(self):
        with mock.patch.object(socket, "getaddrinfo", return_value=[addr("10.0.0.8", 443)]):
            with self.assertRaisesRegex(ValueError, "непубличный IP"):
                osint._validate_public_http_url("https://internal.example")

    def test_domain_intel_rejects_private_dns_before_network_lookups(self):
        with mock.patch.object(socket, "getaddrinfo", return_value=[addr("10.0.0.8", 443)]):
            with mock.patch.object(osint, "_json") as json_lookup:
                with self.assertRaisesRegex(ValueError, "непубличный IP"):
                    osint.domain_intel("internal.example")
        json_lookup.assert_not_called()

    def test_rejects_localhost_hostname(self):
        with self.assertRaisesRegex(ValueError, "Локальные адреса запрещены"):
            osint._validate_public_http_url("http://localhost:8080")

    def test_rejects_non_http_scheme(self):
        with self.assertRaisesRegex(ValueError, "только HTTP и HTTPS"):
            osint._validate_public_http_url("file:///etc/passwd")

    def test_private_ip_intel_does_not_call_external_provider(self):
        with mock.patch.object(osint, "_json") as json_lookup:
            with self.assertRaisesRegex(ValueError, "только для публичных IP"):
                osint.ip_intel("192.168.1.10")
        json_lookup.assert_not_called()

    def test_rejects_credentials_in_url(self):
        with self.assertRaisesRegex(ValueError, "логином или паролем"):
            osint._validate_public_http_url("https://user:pass@example.com")

    def test_allows_public_dns_resolution(self):
        with mock.patch.object(socket, "getaddrinfo", return_value=[addr("8.8.8.8", 443)]):
            parsed = osint._validate_public_http_url("https://example.com/path")
        self.assertEqual(parsed.hostname, "example.com")

    def test_public_fetch_rejects_private_destination_before_connect(self):
        with mock.patch.object(socket, "getaddrinfo", return_value=[addr("192.168.1.1", 80)]):
            with mock.patch.object(socket, "create_connection") as connect:
                with self.assertRaisesRegex(ValueError, "непубличный IP"):
                    osint._get_public_http_url("http://private.example/")
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
