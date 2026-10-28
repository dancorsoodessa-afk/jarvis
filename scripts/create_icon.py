"""Generate a clean JARVIS .ico using only Python's standard library."""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

SIZE = 256
PIXELS = bytearray(SIZE * SIZE * 4)
BG = (4, 12, 22, 255)
CYAN = (42, 225, 255, 255)
PALE = (210, 250, 255, 255)


def blend(x: int, y: int, color: tuple[int, int, int, int], radius: float = 2.0) -> None:
    if not (0 <= x < SIZE and 0 <= y < SIZE):
        return
    i = (y * SIZE + x) * 4
    PIXELS[i:i + 4] = bytes(color)


def dot(cx: float, cy: float, r: float, color: tuple[int, int, int, int]) -> None:
    left, right = max(0, int(cx-r-1)), min(SIZE, int(cx+r+2))
    top, bottom = max(0, int(cy-r-1)), min(SIZE, int(cy+r+2))
    for y in range(top, bottom):
        for x in range(left, right):
            if (x-cx)**2 + (y-cy)**2 <= r*r:
                blend(x, y, color)


def line(x0: float, y0: float, x1: float, y1: float, width: float,
         color: tuple[int, int, int, int]) -> None:
    steps = max(1, int(math.hypot(x1-x0, y1-y0) * 1.5))
    for n in range(steps + 1):
        t = n / steps
        dot(x0 + (x1-x0)*t, y0 + (y1-y0)*t, width/2, color)


def ellipse(cx: float, cy: float, rx: float, ry: float, angle: float,
            width: float, color: tuple[int, int, int, int]) -> None:
    points = []
    ca, sa = math.cos(angle), math.sin(angle)
    for n in range(721):
        t = n * math.tau / 720
        x, y = rx * math.cos(t), ry * math.sin(t)
        points.append((cx + x*ca - y*sa, cy + x*sa + y*ca))
    for a, b in zip(points, points[1:]):
        line(*a, *b, width, color)


# Solid dark background with a restrained cyan frame.
for y in range(SIZE):
    for x in range(SIZE):
        PIXELS[(y*SIZE+x)*4:(y*SIZE+x)*4+4] = bytes(BG)
for inset in (12, 13):
    for x in range(inset, SIZE-inset):
        dot(x, inset, 1, CYAN)
        dot(x, SIZE-inset-1, 1, CYAN)
    for y in range(inset, SIZE-inset):
        dot(inset, y, 1, CYAN)
        dot(SIZE-inset-1, y, 1, CYAN)

# Neural reactor: orbit rings and bright central J.
ellipse(128, 128, 76, 39, -0.72, 2.4, CYAN)
ellipse(128, 128, 76, 39, 0.72, 2.4, (103, 163, 255, 255))
ellipse(128, 128, 57, 57, 0.15, 1.5, (67, 147, 177, 255))
dot(78, 88, 4, PALE)
dot(178, 82, 4, CYAN)
dot(180, 170, 4, PALE)
dot(81, 173, 4, CYAN)

# Geometric J monogram, drawn with thick strokes.
line(103, 91, 153, 91, 9, PALE)
line(145, 91, 145, 145, 9, PALE)
line(145, 145, 137, 159, 9, PALE)
line(137, 159, 119, 166, 9, PALE)
line(119, 166, 103, 158, 9, PALE)

def png_rgba() -> bytes:
    raw = b"".join(b"\x00" + bytes(PIXELS[y*SIZE*4:(y+1)*SIZE*4]) for y in range(SIZE))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">2I5B", SIZE, SIZE, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def main() -> None:
    out = Path("assets/jarvis.ico")
    out.parent.mkdir(parents=True, exist_ok=True)
    png = png_rgba()
    # One 256x256 PNG-backed icon entry; supported by modern Windows.
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    out.write_bytes(header + entry + png)
    print(f"Created {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
