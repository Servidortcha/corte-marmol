from PIL import Image

src = Image.open("static/logo.jpg").convert("RGBA")

# fondo blanco redondeado para que el icono se vea prolijo
background = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
img = src.copy()
img.thumbnail((232, 232), Image.LANCZOS)
offset = ((256 - img.width) // 2, (256 - img.height) // 2)
background.paste(img, offset, img)
background.save("static/icono.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icono generado")
