# -*- coding: utf-8 -*-
"""Логотип Whispy: кнопка Play, собранная из столбиков звуковой волны, на градиенте розовый→фиолетовый.
Генерирует whispy.ico (все размеры) и whispy.png (512) для шапки приложения."""
from PIL import Image, ImageDraw, ImageFilter

PINK, VIOLET, DEEP = (255, 95, 180), (139, 92, 246), (27, 15, 43)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def play_wave(size, bars=None):
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # фон: диагональный градиент + тёмная подложка с мягким свечением
    base = Image.new("RGB", (2, 2))
    base.putdata([PINK, lerp(PINK, VIOLET, 0.5), lerp(PINK, VIOLET, 0.5), VIOLET])
    grad = base.resize((s, s), Image.BILINEAR).convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.24), fill=255)
    img.paste(grad, (0, 0), mask)

    # глубина: тёмная внутренняя область, чтобы белые столбики «светились»
    inner = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(inner).rounded_rectangle([s * 0.09, s * 0.09, s * 0.91, s * 0.91], radius=int(s * 0.19), fill=DEEP + (215,))
    inner = inner.filter(ImageFilter.GaussianBlur(s * 0.01))
    img.alpha_composite(inner)

    # блик сверху
    hl = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([-s * 0.1, -s * 0.55, s * 1.1, s * 0.35], fill=(255, 255, 255, 38))
    hl = hl.filter(ImageFilter.GaussianBlur(s * 0.06))
    img.alpha_composite(Image.composite(hl, Image.new("RGBA", (s, s), (0, 0, 0, 0)), mask))

    # Play-треугольник из столбиков: высокие слева, сходят на нет справа
    if bars is None:
        bars = [0.92, 0.80, 0.66, 0.52, 0.38, 0.24] if size >= 48 else [0.9, 0.62, 0.34]
    n = len(bars)
    gap = s * (0.055 if n > 3 else 0.09)
    bw = (s * 0.56 - gap * (n - 1)) / n
    total = bw * n + gap * (n - 1)
    x0 = (s - total) / 2 + s * 0.02

    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    x = x0
    for i, h in enumerate(bars):
        bh = s * 0.62 * h
        y0 = (s - bh) / 2
        gd.rounded_rectangle([x, y0, x + bw, y0 + bh], radius=bw / 2, fill=lerp(PINK, VIOLET, i / max(1, n - 1)) + (200,))
        x += bw + gap
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.045))
    img.alpha_composite(glow)

    d = ImageDraw.Draw(img)
    x = x0
    for i, h in enumerate(bars):
        bh = s * 0.62 * h
        y0 = (s - bh) / 2
        col = lerp((255, 255, 255), lerp(PINK, VIOLET, i / max(1, n - 1)), 0.0 if i == 0 else min(0.55, 0.12 * i))
        d.rounded_rectangle([x, y0, x + bw, y0 + bh], radius=bw / 2, fill=col + (255,))
        x += bw + gap

    # тонкая светлая кромка
    d.rounded_rectangle([s * 0.006, s * 0.006, s * 0.994, s * 0.994], radius=int(s * 0.24), outline=(255, 255, 255, 70), width=max(1, s // 160))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [256, 128, 64, 48, 32, 24, 16]
    imgs = [play_wave(sz) for sz in sizes]
    imgs[0].save("whispy.ico", format="ICO", sizes=[(sz, sz) for sz in sizes], append_images=imgs[1:])
    play_wave(512).save("whispy.png")
    print("whispy.ico OK")
