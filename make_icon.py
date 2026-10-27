# -*- coding: utf-8 -*-
"""Иконка whispy.ico: градиент розовый→фиолетовый, белая звуковая волна.
Каждый размер рисуется отдельно, чтобы в 16–32 px волна оставалась читаемой."""
from PIL import Image, ImageDraw, ImageFilter


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make(size):
    s = size * 4
    c1, c2 = (255, 95, 180), (139, 92, 246)
    base = Image.new("RGB", (2, 2))
    base.putdata([c1, lerp(c1, c2, 0.5), lerp(c1, c2, 0.5), c2])
    grad = base.resize((s, s), Image.BILINEAR).convert("RGBA")

    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.24, fill=255)
    img.paste(grad, (0, 0), mask)

    # блик сверху
    hl = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([-s * 0.2, -s * 0.7, s * 1.2, s * 0.45], fill=(255, 255, 255, 60))
    hl = hl.filter(ImageFilter.GaussianBlur(s * 0.08))
    img.alpha_composite(Image.composite(hl, Image.new("RGBA", (s, s), (0, 0, 0, 0)), mask))

    # волна: меньше столбиков на маленьких размерах
    if size <= 24:
        bars = [0.45, 0.9, 0.55]
        w, gap = s * 0.16, s * 0.11
    elif size <= 48:
        bars = [0.35, 0.65, 0.95, 0.65, 0.35]
        w, gap = s * 0.10, s * 0.06
    else:
        bars = [0.3, 0.55, 0.85, 1.0, 0.85, 0.55, 0.3]
        w, gap = s * 0.075, s * 0.045
    total = len(bars) * w + (len(bars) - 1) * gap
    x = (s - total) / 2
    d = ImageDraw.Draw(img)
    for h in bars:
        bh = s * 0.6 * h
        y0 = (s - bh) / 2
        d.rounded_rectangle([x, y0, x + w, y0 + bh], radius=w / 2, fill=(255, 255, 255, 255))
        x += w + gap
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [256, 128, 64, 48, 32, 24, 16]
    imgs = [make(sz) for sz in sizes]
    imgs[0].save("whispy.ico", format="ICO", sizes=[(sz, sz) for sz in sizes], append_images=imgs[1:])
    imgs[0].save("whispy.png")
    print("whispy.ico создан")
