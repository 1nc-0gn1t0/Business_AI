"""Extract a bounded 2D rig from the owner's original B image; no generated parts."""

import argparse
import hashlib
import json
from collections import deque
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "apps/web/src/assets/vi"
BOX = (90, 100, 830, 885)
OUTLINE = [
    (500, 239),
    (506, 224),
    (560, 181),
    (625, 142),
    (695, 116),
    (742, 111),
    (746, 117),
    (737, 141),
    (715, 170),
    (677, 191),
    (742, 184),
    (775, 181),
    (781, 187),
    (776, 205),
    (751, 235),
    (718, 252),
    (773, 263),
    (795, 263),
    (801, 269),
    (794, 291),
    (775, 324),
    (752, 355),
    (771, 388),
    (784, 439),
    (787, 490),
    (783, 545),
    (785, 582),
    (798, 623),
    (813, 671),
    (817, 726),
    (806, 766),
    (792, 792),
    (774, 799),
    (756, 790),
    (750, 808),
    (731, 836),
    (702, 853),
    (676, 861),
    (647, 849),
    (623, 818),
    (562, 812),
    (528, 813),
    (480, 813),
    (451, 819),
    (433, 841),
    (411, 850),
    (377, 843),
    (352, 819),
    (325, 811),
    (291, 794),
    (267, 770),
    (246, 738),
    (229, 699),
    (201, 687),
    (160, 664),
    (132, 634),
    (110, 599),
    (104, 568),
    (108, 543),
    (121, 520),
    (142, 505),
    (165, 501),
    (186, 511),
    (205, 525),
    (215, 535),
    (226, 483),
    (245, 432),
    (277, 386),
    (315, 347),
    (366, 312),
    (419, 281),
    (459, 262),
]
PARTS = {
    "hand": [
        (215, 535),
        (225, 575),
        (231, 607),
        (246, 650),
        (254, 676),
        (243, 694),
        (220, 696),
        (189, 682),
        (156, 660),
        (128, 631),
        (111, 603),
        (104, 574),
        (106, 548),
        (118, 523),
        (142, 505),
        (165, 501),
        (186, 511),
        (205, 525),
    ],
    "plume1": [
        (503, 240),
        (540, 206),
        (600, 158),
        (695, 120),
        (742, 111),
        (746, 115),
        (735, 144),
        (710, 176),
        (665, 197),
        (594, 218),
        (525, 240),
    ],
    "plume2": [
        (556, 249),
        (610, 218),
        (688, 194),
        (772, 183),
        (781, 185),
        (775, 205),
        (751, 234),
        (713, 252),
        (653, 265),
        (600, 266),
    ],
    "plume3": [
        (644, 277),
        (688, 269),
        (774, 264),
        (797, 265),
        (800, 269),
        (794, 289),
        (774, 323),
        (751, 351),
        (734, 338),
        (711, 317),
        (681, 296),
    ],
    "eye_left": [
        (366, 442),
        (379, 445),
        (388, 456),
        (392, 477),
        (386, 501),
        (378, 522),
        (366, 531),
        (351, 529),
        (337, 521),
        (333, 507),
        (335, 480),
        (341, 458),
        (352, 447),
    ],
    "eye_right": [
        (601, 471),
        (614, 474),
        (622, 487),
        (624, 508),
        (620, 534),
        (613, 549),
        (601, 558),
        (583, 558),
        (570, 551),
        (563, 539),
        (563, 518),
        (568, 493),
        (579, 479),
        (589, 473),
    ],
}


def mask(points: list[tuple[int, int]], size: tuple[int, int]) -> Image.Image:
    image = Image.new("L", (size[0] * 3, size[1] * 3))
    ImageDraw.Draw(image).polygon(
        [((x - BOX[0]) * 3, (y - BOX[1]) * 3) for x, y in points], fill=255
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def build(source: Path) -> None:
    provenance = json.loads((ASSETS / "provenance.json").read_text(encoding="utf8"))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != provenance["sources"]["B"]["sha256"]:
        raise ValueError("Expected the original user-supplied B image; hash mismatch")
    image = Image.open(source).convert("RGBA").crop(BOX)
    silhouette = mask(OUTLINE, image.size).filter(ImageFilter.MaxFilter(19))
    # Remove only near-white exterior connected to the canvas border. Body pixels
    # behind the original blue rim stay enclosed; no global white-key removal.
    exterior = Image.new("L", image.size)
    queue = deque((x, y) for x in range(image.width) for y in (0, image.height - 1))
    queue.extend((x, y) for y in range(image.height) for x in (0, image.width - 1))
    seen = set()
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen or x < 0 or y < 0 or x >= image.width or y >= image.height:
            continue
        seen.add((x, y))
        if min(image.getpixel((x, y))[:3]) <= 246:
            continue
        exterior.putpixel((x, y), 255)
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    silhouette = ImageChops.subtract(silhouette, exterior).filter(
        ImageFilter.GaussianBlur(0.45)
    )
    # The original ground shadow is not a limb: trace the visible foot contour.
    floor = [
        (0, 785),
        (180, 650),
        (200, 675),
        (220, 703),
        (240, 721),
        (260, 733),
        (280, 740),
        (300, 744),
        (320, 740),
        (340, 731),
        (360, 716),
        (380, 710),
        (400, 713),
        (420, 713),
        (440, 715),
        (460, 732),
        (480, 747),
        (500, 756),
        (520, 760),
        (540, 761),
        (560, 757),
        (580, 746),
        (600, 727),
        (620, 703),
        (640, 785),
        (740, 785),
    ]
    floor_mask = Image.new("L", image.size)
    ImageDraw.Draw(floor_mask).polygon([(0, 0), (740, 0), *reversed(floor)], fill=255)
    silhouette = ImageChops.multiply(
        silhouette, floor_mask.filter(ImageFilter.GaussianBlur(0.7))
    )
    head = [
        (400, 149),
        (450, 152),
        (500, 165),
        (550, 186),
        (600, 218),
        (640, 258),
        (660, 295),
        (740, 360),
    ]
    for (x0, y0), (x1, y1) in pairwise(head):
        for x in range(x0, x1):
            height = max(0, round(y0 + (y1 - y0) * (x - x0) / (x1 - x0)) - 16)
            for y in range(height):
                red, _green, blue, _ = image.getpixel((x, y))
                if blue - red < 45:
                    silhouette.putpixel((x, y), 0)
    ImageDraw.Draw(silhouette).rectangle((396, 130, 410, 145), fill=0)
    keep = Image.new("L", image.size)
    seen_alpha = set()
    for y in range(image.height):
        for x in range(image.width):
            if (x, y) in seen_alpha or silhouette.getpixel((x, y)) < 64:
                continue
            component = []
            queue = deque([(x, y)])
            while queue:
                px, py = queue.popleft()
                if (
                    (px, py) in seen_alpha
                    or px < 0
                    or py < 0
                    or px >= image.width
                    or py >= image.height
                ):
                    continue
                seen_alpha.add((px, py))
                if silhouette.getpixel((px, py)) < 64:
                    continue
                component.append((px, py))
                queue.extend(((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)))
            if len(component) >= 1000:
                for point in component:
                    keep.putpixel(point, 255)
    # Keep antialiased rims of the actual character, not detached low-alpha residue.
    silhouette = ImageChops.multiply(silhouette, keep.filter(ImageFilter.MaxFilter(5)))
    silhouette = (
        silhouette.filter(ImageFilter.MaxFilter(3))
        .filter(ImageFilter.MinFilter(3))
        .filter(ImageFilter.GaussianBlur(0.55))
    )
    base = image.copy()
    base.putalpha(silhouette)
    parts = {
        name: ImageChops.multiply(mask(points, image.size), silhouette)
        for name, points in PARTS.items()
    }
    for name in ("eye_left", "eye_right"):
        parts[name] = parts[name].filter(ImageFilter.MaxFilter(5))
    for name, part in parts.items():
        if name.startswith("eye_"):
            # Restore only the hidden face-surface gradient, not new facial features.
            bounds = part.getbbox()
            assert bounds is not None
            left, top, right, bottom = bounds
            patch = base.copy()
            for y in range(top, bottom):
                a, b = image.getpixel((left - 3, y)), image.getpixel((right + 3, y))
                for x in range(left, right):
                    t = (x - left) / (right - left)
                    patch.putpixel(
                        (x, y),
                        tuple(round(a[c] * (1 - t) + b[c] * t) for c in range(3))
                        + (255,),
                    )
            base = Image.composite(
                patch, base, part.filter(ImageFilter.GaussianBlur(0.5))
            )
        else:
            erase = part.copy()
            if name == "hand":
                # Keep an original wrist overlap; do not invent an occluded torso.
                ImageDraw.Draw(erase).rectangle(
                    (228 - BOX[0], 0, image.width, image.height), fill=0
                )
            base.putalpha(ImageChops.subtract(base.getchannel("A"), erase))
    output = ASSETS / "motion"
    output.mkdir(exist_ok=True)
    manifest = {
        "source_sha256": digest,
        "source_crop": BOX,
        "canvas": image.size,
        "method": "Manual silhouette/part mattes, original wrist overlap; face-surface interpolation only under extracted eyes. WebP94. No AI or hidden limb reconstruction.",
        "layers": {},
    }
    for name, part in {"body": None, **parts}.items():
        layer = base if part is None else image.copy()
        if part is not None:
            layer.putalpha(part)
        bounds = (0, 0, image.width, image.height) if part is None else part.getbbox()
        assert bounds is not None
        destination = output / f"{name}.webp"
        layer.crop(bounds).save(destination, "WEBP", quality=94, method=6)
        manifest["layers"][name] = {
            "bounds": bounds,
            "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    (output / "provenance.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf8"
    )
    print(
        "Motion layers:",
        len(manifest["layers"]),
        "bytes:",
        sum(v["bytes"] for v in manifest["layers"].values()),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    build(parser.parse_args().source)
