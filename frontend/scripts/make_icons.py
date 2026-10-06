# Иконки PWA из той же геометрии, что favicon.svg.
# uv run --with pillow python frontend/scripts/make_icons.py frontend/public
"""Иконки Veillou: полумесяц и звезда на тёмном фоне. Геометрия совпадает с favicon.svg."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

BG = (18, 16, 32)        # #121020
MOON = (196, 181, 253)   # #c4b5fd (violet-300)
STAR = (250, 204, 21)    # #facc15
OUT = Path(sys.argv[1])

# Координаты в системе 512x512 (как viewBox SVG), масштаб s — доля «полезной» зоны
def draw(size: int, scale: float, rounded: bool) -> Image.Image:
    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 512
    if rounded:
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(112 * k), fill=BG)
    else:
        d.rectangle([0, 0, S, S], fill=BG)
    def t(x, y):  # масштаб вокруг центра
        return (256 + (x - 256) * scale) * k, (256 + (y - 256) * scale) * k
    def circle(cx, cy, r, fill):
        x0, y0 = t(cx - r, cy - r); x1, y1 = t(cx + r, cy + r)
        d.ellipse([x0, y0, x1, y1], fill=fill)
    circle(236, 276, 150, MOON)
    circle(306, 216, 128, BG)
    # звезда-ромб
    cx, cy, r = 340, 176, 44
    pts = [t(cx, cy - r), t(cx + r * 0.32, cy - r * 0.32), t(cx + r, cy), t(cx + r * 0.32, cy + r * 0.32),
           t(cx, cy + r), t(cx - r * 0.32, cy + r * 0.32), t(cx - r, cy), t(cx - r * 0.32, cy - r * 0.32)]
    d.polygon(pts, fill=STAR)
    return img.resize((size, size), Image.LANCZOS)

draw(192, 1.0, True).save(OUT / "pwa-192.png")
draw(512, 1.0, True).save(OUT / "pwa-512.png")
draw(512, 0.78, False).save(OUT / "pwa-maskable-512.png")
draw(180, 0.86, False).convert("RGB").save(OUT / "apple-touch-icon.png")

# Бейдж уведомлений Android: только альфа-канал, белый месяц
def badge(size: int) -> Image.Image:
    ss = 4; S = size * ss; k = S / 512
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = Image.new("L", (S, S), 0); d = ImageDraw.Draw(m)
    d.ellipse([(236-170)*k, (276-170)*k, (236+170)*k, (276+170)*k], fill=255)
    d.ellipse([(316-145)*k, (206-145)*k, (316+145)*k, (206+145)*k], fill=0)
    img.paste((255, 255, 255, 255), mask=m)
    return img.resize((size, size), Image.LANCZOS)

badge(96).save(OUT / "badge-96.png")
