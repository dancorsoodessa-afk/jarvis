"""Local-first OSINT helpers for JARVIS.

No API key is required. Network lookups use public RDAP/IP endpoints and
standard HTTP. Results are intentionally evidence-oriented and concise.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

from .web import USER_AGENT, TIMEOUT


def _get(url: str, timeout: int = TIMEOUT) -> tuple[int, dict[str, str], bytes]:
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
    lines = [f"OSINT: {domain}"]
    try:
        infos = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
        ips = sorted({item[4][0] for item in infos})
        lines.append("IP: " + ", ".join(ips))
    except OSError as exc:
        lines.append(f"DNS/IP: ошибка {exc}")

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
        with socket.create_connection((domain, 443), timeout=TIMEOUT) as sock:
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
    status, headers, body = _get(value)
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
