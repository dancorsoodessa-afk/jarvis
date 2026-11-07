"""Local-first OSINT helpers for JARVIS.

No API key is required. Network lookups use public RDAP/IP endpoints and
standard HTTP. Results are intentionally evidence-oriented and concise.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

from .web import USER_AGENT, TIMEOUT


def _parse_public_http_url(value: str):
    """Parse an HTTP URL and pin every resolved address to a public IP."""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Разрешены только HTTP и HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("URL с логином или паролем запрещён")
    host = parsed.hostname
    if not host or host.lower() == "localhost" or host.lower().endswith((".localhost", ".local")):
        raise ValueError("Локальные адреса запрещены для OSINT URL")
    try:
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme.lower() == "https" else 80
        if not 1 <= port <= 65535:
            raise ValueError("Некорректный порт URL")
    except ValueError as exc:
        raise ValueError("Некорректный порт URL") from exc
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Не удалось проверить DNS-адрес URL: {exc}") from exc
    addresses = []
    for record in records:
        try:
            ip = ipaddress.ip_address(record[4][0].split("%", 1)[0])
        except ValueError as exc:
            raise ValueError("DNS вернул некорректный IP-адрес") from exc
        if not ip.is_global:
            raise ValueError(f"Доступ к непубличному IP запрещён: {ip}")
        if str(ip) not in addresses:
            addresses.append(str(ip))
    if not addresses:
        raise ValueError("Домен URL не имеет публичных IP-адресов")
    return parsed, addresses


def _validate_public_http_url(value: str):
    """Compatibility validator used by tests and callers."""
    return _parse_public_http_url(value)[0]


def _get_public_http_url(value: str, timeout: int = TIMEOUT) -> tuple[int, dict[str, str], bytes]:
    """Fetch a public URL while connecting to the exact IPs validated by DNS.

    Every redirect is independently resolved and checked. The socket connects
    to the validated IP, while HTTP Host and TLS SNI retain the original domain.
    """
    current = value
    for redirect_count in range(6):
        parsed, addresses = _parse_public_http_url(current)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        target = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        last_error = None
        response_data = None

        for address in addresses:
            connection = None
            try:
                if parsed.scheme.lower() == "https":
                    connection = http.client.HTTPSConnection(
                        host, port, timeout=timeout, context=ssl.create_default_context()
                    )
                    raw_socket = socket.create_connection((address, port), timeout=timeout)
                    connection.sock = connection._context.wrap_socket(raw_socket, server_hostname=host)
                else:
                    connection = http.client.HTTPConnection(host, port, timeout=timeout)
                    connection.sock = socket.create_connection((address, port), timeout=timeout)

                connection.request("GET", target, headers={"User-Agent": USER_AGENT})
                response = connection.getresponse()
                body = response.read(2_000_000)
                headers = dict(response.getheaders())
                response_data = (response.status, headers, body)
                break
            except Exception as exc:
                last_error = exc
            finally:
                if connection is not None:
                    connection.close()

        if response_data is None:
            raise RuntimeError(f"Не удалось подключиться к публичному адресу: {last_error}")

        status, headers, body = response_data
        location = next((value for key, value in headers.items() if key.lower() == "location"), None)
        if status in {301, 302, 303, 307, 308} and location:
            if redirect_count >= 5:
                raise RuntimeError("Превышен лимит перенаправлений URL")
            current = urllib.parse.urljoin(current, location)
            continue
        return status, headers, body

    raise RuntimeError("Превышен лимит перенаправлений URL")


def _get(url: str, timeout: int = TIMEOUT) -> tuple[int, dict[str, str], bytes]:
    """Fetch a fixed, trusted service endpoint (RDAP/IP metadata)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read(2_000_000)
    except Exception as exc:
        raise RuntimeError(f"HTTP ошибка: {exc}") from exc

def _json(url: str) -> dict:
    status, _, body = _get(url)
    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status}: {url}")
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ответ не JSON: {url}") from exc


def _domain(value: str) -> str:
    value = value.strip()
    if "://" in value:
        value = urllib.parse.urlparse(value).hostname or value
    value = value.split("/")[0].split(":")[0].strip().lower().rstrip(".")
    if not value or "." not in value:
        raise ValueError("Нужен домен, например example.com")
    return value


def domain_intel(value: str) -> str:
    domain = _domain(value)
    # Resolve once, validate, then connect to one of those exact public IPs.
    _parsed, ips = _parse_public_http_url(f"https://{domain}")
    lines = [f"OSINT: {domain}", "IP: " + ", ".join(ips)]

    try:
        rdap = _json(f"https://rdap.org/domain/{urllib.parse.quote(domain)}")
        lines.append(f"RDAP handle: {rdap.get('handle', '—')}")
        status = rdap.get("status") or []
        if status:
            lines.append("Статус: " + ", ".join(map(str, status)))
        events = rdap.get("events") or []
        for event in events[:6]:
            if isinstance(event, dict) and event.get("eventAction") and event.get("eventDate"):
                lines.append(f"{event['eventAction']}: {event['eventDate']}")
        nameservers = []
        for ent in rdap.get("nameservers") or []:
            if isinstance(ent, dict) and ent.get("ldhName"):
                nameservers.append(ent["ldhName"])
        if nameservers:
            lines.append("NS: " + ", ".join(nameservers[:8]))
    except Exception as exc:
        lines.append(f"RDAP: {exc}")

    try:
        context = ssl.create_default_context()
        with socket.create_connection((ips[0], 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert()
                subject = dict(x[0] for x in cert.get("subject", []))
                issuer = dict(x[0] for x in cert.get("issuer", []))
                lines.append(f"TLS CN: {subject.get('commonName', '—')}")
                lines.append(f"TLS issuer: {issuer.get('commonName', '—')}")
                lines.append(f"TLS expires: {cert.get('notAfter', '—')}")
    except Exception as exc:
        lines.append(f"TLS: {exc}")
    return "\n".join(lines)


def ip_intel(value: str) -> str:
    value = value.strip()
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("Нужен IPv4 или IPv6 адрес") from exc
    try:
        data = _json(f"https://ipwho.is/{urllib.parse.quote(value)}")
    except Exception as exc:
        return f"IP OSINT {value}\nОшибка: {exc}"
    fields = [
        ("Страна", data.get("country")), ("Регион", data.get("region")),
        ("Город", data.get("city")), ("Организация", data.get("connection", {}).get("org") if isinstance(data.get("connection"), dict) else None),
        ("ASN", data.get("connection", {}).get("asn") if isinstance(data.get("connection"), dict) else None),
        ("Провайдер", data.get("connection", {}).get("isp") if isinstance(data.get("connection"), dict) else None),
        ("Timezone", data.get("timezone", {}).get("id") if isinstance(data.get("timezone"), dict) else None),
    ]
    return "IP OSINT: " + value + "\n" + "\n".join(f"{k}: {v}" for k, v in fields if v not in (None, ""))


def url_intel(value: str) -> str:
    value = value.strip()
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if not parsed.hostname:
        raise ValueError("Некорректный URL")
    status, headers, body = _get_public_http_url(value)
    text = body.decode("utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    links = []
    for href in re.findall(r"href=[\"']([^\"']+)", text, re.I):
        absolute = urllib.parse.urljoin(value, href)
        if absolute.startswith(("http://", "https://")) and absolute not in links:
            links.append(absolute)
        if len(links) >= 12:
            break
    digest = hashlib.sha256(body).hexdigest()
    lines = [
        f"URL: {value}", f"HTTP: {status}", f"Host: {parsed.hostname}",
        f"Title: {(title.group(1).strip() if title else '—')[:300]}",
        f"SHA-256(body): {digest}",
    ]
    for key in ("Server", "Content-Type", "Last-Modified", "ETag"):
        if key in headers:
            lines.append(f"{key}: {headers[key]}")
    if links:
        lines.append("Ссылки:\n" + "\n".join(f"- {x}" for x in links))
    return "\n".join(lines)


def email_intel(value: str) -> str:
    email = value.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Некорректный email")
    domain = email.rsplit("@", 1)[1]
    result = [f"Email OSINT: {email}", f"Домен: {domain}"]
    try:
        result.append(domain_intel(domain))
    except Exception as exc:
        result.append(f"Домен: {exc}")
    result.append("Примечание: существование конкретного почтового ящика без отправки письма надёжно не подтверждается.")
    return "\n".join(result)


def username_search(username: str) -> str:
    username = username.strip().lstrip("@").split()[0]
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", username):
        raise ValueError("Некорректное имя пользователя")
    sites = {
        "GitHub": f"https://github.com/{username}",
        "GitLab": f"https://gitlab.com/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}/",
        "X": f"https://x.com/{username}",
        "Telegram": f"https://t.me/{username}",
    }
    lines = [f"Username OSINT: {username}"]
    for name, url in sites.items():
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                lines.append(f"{name}: HTTP {resp.status} — {url}")
        except Exception as exc:
            code = getattr(exc, "code", None)
            lines.append(f"{name}: {'HTTP ' + str(code) if code else 'нет подтверждения'} — {url}")
    return "\n".join(lines)


def image_metadata(path: str) -> str:
    try:
        from PIL import Image, ExifTags
    except Exception as exc:
        raise RuntimeError("Для image_metadata нужен Pillow") from exc
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"Файл не найден: {file}")
    with Image.open(file) as img:
        lines = [f"Файл: {file}", f"Формат: {img.format}", f"Размер: {img.size}", f"Режим: {img.mode}"]
        exif = img.getexif()
        if exif:
            for key, value in exif.items():
                name = ExifTags.TAGS.get(key, str(key))
                if name in {"GPSInfo", "DateTime", "DateTimeOriginal", "Make", "Model", "Software"}:
                    lines.append(f"{name}: {value}")
        lines.append(f"SHA-256: {hashlib.sha256(file.read_bytes()).hexdigest()}")
    return "\n".join(lines)


def investigate(target: str) -> str:
    target = target.strip()
    if not target:
        raise ValueError("Укажите домен, URL, IP, email или username")
    if "@" in target and " " not in target:
        return email_intel(target)
    try:
        ipaddress.ip_address(target)
        return ip_intel(target)
    except ValueError:
        pass
    if "://" in target or "/" in target:
        return url_intel(target)
    if "." in target:
        return domain_intel(target)
    return username_search(target)
