"""Genera un logo limpio para La Puntual Marmoleria (monograma LP en piedra)."""

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 512
W, H = SIZE, SIZE
FONT_B = r"C:\Windows\Fonts\arialbd.ttf"
FONT_R = r"C:\Windows\Fonts\arial.ttf"


def _gradient(size, top, bottom):
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(size[1]):
        t = y / size[1]
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (size[0], y)], fill=color)
    return img


def _rounded(image, radius):
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, image.size[0] - 1, image.size[1] - 1],
                           radius=radius, fill=255)
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    out.paste(image, (0, 0), mask)
    return out


def build():
    base = _gradient((W, H), (78, 86, 94), (44, 50, 56))

    # vetas de marmol (lineas claras suaves)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    veins = [
        ((60, 150), (300, 120)),
        ((90, 300), (340, 280)),
        ((200, 60), (460, 200)),
        ((40, 420), (260, 380)),
    ]
    for a, b in veins:
        draw.line([a, b], fill=(255, 255, 255, 26), width=10)
    overlay = overlay.filter(ImageFilter.GaussianBlur(6))
    base = Image.alpha_composite(base.convert("RGBA"), overlay)

    # marco interior
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([18, 18, W - 19, H - 19], radius=46,
                           outline=(255, 255, 255, 120), width=5)

    # monograma LP
    font = ImageFont.truetype(FONT_B, 190)
    text = "LP"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (W - tw) / 2 - bbox[0]
    ty = 118 - bbox[1]
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # marca debajo
    font_small = ImageFont.truetype(FONT_B, 34)
    line1 = "LA PUNTUAL"
    b1 = draw.textbbox((0, 0), line1, font=font_small)
    draw.text(((W - (b1[2] - b1[0])) / 2 - b1[0], 348 - b1[1]),
              line1, font=font_small, fill=(255, 255, 255, 255))

    font_tiny = ImageFont.truetype(FONT_R, 26)
    line2 = "MARMOLERIA"
    b2 = draw.textbbox((0, 0), line2, font=font_tiny)
    draw.text(((W - (b2[2] - b2[0])) / 2 - b2[0], 396 - b2[1]),
              line2, font=font_tiny, fill=(214, 220, 226, 255))

    logo = _rounded(base, 60)
    logo.save("static/logo.png")
    print("logo generado: static/logo.png")


if __name__ == "__main__":
    build()
