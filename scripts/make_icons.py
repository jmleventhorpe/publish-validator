"""Draw the status icons used by the Blender panel.

    python scripts/make_icons.py

Writes 64x64 PNGs into src/publish_validator/hosts/blender/icons/. The PNGs are
committed, so this only needs running again when the icons change. Plain Python,
no libraries: each pixel is sampled 4x4 times for smooth edges.
"""

import itertools
import math
import struct
import zlib
from pathlib import Path

SIZE = 64
SAMPLES = 4
OUT = Path(__file__).resolve().parents[1] / "src/publish_validator/hosts/blender/icons"

GREEN = (64, 168, 82)
ORANGE = (232, 146, 36)
RED = (220, 66, 66)
MAGENTA = (184, 76, 184)
GREY = (128, 133, 140)
WHITE = (255, 255, 255)


# Shapes: functions that say whether a point (x, y) is inside. y points down.


def circle(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def ring(cx, cy, outer, inner):
    return lambda x, y: inner * inner <= (x - cx) ** 2 + (y - cy) ** 2 <= outer * outer


def stroke(points, width):
    """A thick line through the points, with round ends and joints."""
    segments = list(itertools.pairwise(points))

    def inside(x, y):
        for (x1, y1), (x2, y2) in segments:
            dx, dy = x2 - x1, y2 - y1
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
            if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) <= width:
                return True
        return False

    return inside


def triangle(a, b, c):
    def side(p, q, x, y):
        return (q[0] - p[0]) * (y - p[1]) - (q[1] - p[1]) * (x - p[0])

    def inside(x, y):
        s1, s2, s3 = side(a, b, x, y), side(b, c, x, y), side(c, a, x, y)
        return (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)

    return inside


def either(*shapes):
    return lambda x, y: any(shape(x, y) for shape in shapes)


def exclamation(top, bottom, dot):
    return either(stroke([(32, top), (32, bottom)], 3.6), circle(32, dot, 3.8))


# Each icon: a list of (shape, colour) layers, later layers drawn on top.
BADGE = circle(32, 32, 29)
ICONS = {
    "passed": [(BADGE, GREEN), (stroke([(19, 33), (28, 42), (45, 23)], 4.2), WHITE)],
    "fixed": [(BADGE, GREEN), (stroke([(19, 33), (28, 42), (45, 23)], 4.2), WHITE)],
    "failed": [
        (BADGE, RED),
        (stroke([(22, 22), (42, 42)], 4.2), WHITE),
        (stroke([(42, 22), (22, 42)], 4.2), WHITE),
    ],
    "warning": [(triangle((32, 5), (61, 57), (3, 57)), ORANGE), (exclamation(22, 39, 48), WHITE)],
    "errored": [(BADGE, MAGENTA), (exclamation(15, 35, 46), WHITE)],
    "skipped": [(BADGE, GREY), (stroke([(20, 32), (44, 32)], 4.2), WHITE)],
    "not_run": [(ring(32, 32, 28, 22), GREY)],
}


def render(layers):
    rows = []
    step = 1 / SAMPLES
    for py in range(SIZE):
        row = bytearray()
        for px in range(SIZE):
            r = g = b = a = 0.0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x, y = px + (sx + 0.5) * step, py + (sy + 0.5) * step
                    colour = None
                    for shape, layer_colour in layers:
                        if shape(x, y):
                            colour = layer_colour
                    if colour:
                        r, g, b, a = r + colour[0], g + colour[1], b + colour[2], a + 1
            count = SAMPLES * SAMPLES
            if a:
                row += bytes((round(r / a), round(g / a), round(b / a), round(255 * a / count)))
            else:
                row += bytes(4)
        rows.append(bytes(row))
    return rows


def write_png(path, rows):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + row for row in rows)  # filter type 0 on every row
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # 8-bit RGBA
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, layers in ICONS.items():
        write_png(OUT / f"{name}.png", render(layers))
        print(f"wrote {OUT / name}.png")


if __name__ == "__main__":
    main()
