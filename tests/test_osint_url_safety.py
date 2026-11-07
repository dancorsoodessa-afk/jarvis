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

    def test_rejects_localhost_hostname(self):
        with self.assertRaisesRegex(ValueError, "Локальные адреса запрещены"):
            osint._validate_public_http_url("http://localhost:8080")

    def test_rejects_non_http_scheme(self):
        with self.assertRaisesRegex(ValueError, "только HTTP и HTTPS"):
            osint._validate_public_http_url("file:///etc/passwd")

    def test_rejects_credentials_in_url(self):
        with self.assertRaisesRegex(ValueError, "логином или паролем"):
            osint._validate_public_http_url("https://user:pass@example.com")

    def test_allows_public_dns_resolution(self):
        with mock.patch.object(socket, "getaddrinfo", return_value=[addr("8.8.8.8", 443)]):
            parsed = osint._validate_public_http_url("https://example.com/path")
        self.assertEqual(parsed.hostname, "example.com")

    def test_redirect_handler_rejects_private_destination(self):
        handler = osint._PublicOnlyRedirectHandler()
        with mock.patch.object(socket, "getaddrinfo", return_value=[addr("192.168.1.1", 80)]):
            with self.assertRaisesRegex(ValueError, "непубличный IP"):
                handler.redirect_request(
                    mock.Mock(), mock.Mock(), 302, "Found", {}, "http://router.local/"
                )


if __name__ == "__main__":
    unittest.main()
