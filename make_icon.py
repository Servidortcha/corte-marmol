from PIL import Image

src = Image.open("static/icono_aresa.png").convert("RGBA").resize((256, 256), Image.LANCZOS)
src.save("static/icono.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icono generado")
