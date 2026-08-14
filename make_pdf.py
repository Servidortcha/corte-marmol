from fpdf import FPDF

FONT = r"C:\Windows\Fonts\arial.ttf"
FONT_B = r"C:\Windows\Fonts\arialbd.ttf"


def mc(pdf, w, h, text):
    pdf.multi_cell(w, h, text)
    pdf.set_x(pdf.l_margin)


def build():
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("Arial", "", FONT)
    pdf.add_font("Arial", "B", FONT_B)

    # ---------- Portada ----------
    pdf.add_page()
    pdf.set_fill_color(58, 64, 70)
    pdf.rect(0, 0, 210, 42, "F")
    pdf.image("static/logo.png", x=14, y=8, w=26)
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(244, 245, 246)
    pdf.set_xy(45, 12)
    mc(pdf, 150, 10, "Aresa-Nest")
    pdf.set_font("Arial", "", 12)
    pdf.set_xy(45, 24)
    mc(pdf, 150, 8, "Optimizacion de corte de marmol en planchas")

    pdf.set_text_color(30, 30, 30)
    pdf.set_y(60)
    pdf.set_font("Arial", "B", 17)
    mc(pdf, 0, 10, "Guia de instalacion y uso")
    pdf.ln(2)
    pdf.set_font("Arial", "", 11)
    mc(pdf, 0, 6,
        "Esta aplicacion calcula el mejor agrupamiento de las piezas de marmol "
        "sobre las planchas disponibles, respetando el ancho de la hoja de sierra "
        "y la separacion por color de linea (ingletes).\n\n"
        "Puede usarse sin conexion a internet y no requiere instalar nada mas: "
        "es un programa autocontenido que funciona en Windows 10 y Windows 11.")

    pdf.ln(3)
    pdf.set_font("Arial", "B", 13)
    mc(pdf, 0, 8, "Requisitos del sistema")
    pdf.set_font("Arial", "", 11)
    for item in [
        "Windows 10 o Windows 11 (64 bits).",
        "Componente WebView2 (viene incluido en Windows 10/11 actualizados; "
        "si no, Windows pide instalarlo automaticamente).",
        "Sin necesidad de conexion a internet ni de Python.",
    ]:
        mc(pdf, 0, 6, "- " + item)

    pdf.ln(2)
    pdf.set_font("Arial", "B", 13)
    mc(pdf, 0, 8, "Archivos que recibe")
    pdf.set_font("Arial", "", 11)
    mc(pdf, 0, 6,
        "El programa se entrega como un unico archivo: LaPuntualMarmoleria.exe "
        "(aprox. 35 MB). Junto a el puede ir esta guia en PDF.")

    pdf.ln(2)
    pdf.set_font("Arial", "B", 13)
    mc(pdf, 0, 8, "Instalacion")
    pdf.set_font("Arial", "", 11)
    steps = [
        "Copiar el archivo LaPuntualMarmoleria.exe a la carpeta donde se quiera "
        "usar (por ejemplo C:\\Marmoleria\\ o el Escritorio).",
        "Doble clic sobre el archivo para abrirlo. La primera apertura puede "
        "tardar unos segundos.",
        "Si Windows muestra el aviso de seguridad, pulsar \"Mas informacion\" y "
        "luego \"Ejecutar de todas formas\" (es un programa propio, sin firma "
        "digital).",
        "La ventana de la aplicacion se abre sola. No hace falta abrir un "
        "navegador.",
        "Para mayor comodidad, se puede crear un acceso directo del exe en el "
        "Escritorio (clic derecho, Enviar a, Escritorio).",
    ]
    for i, step in enumerate(steps, start=1):
        mc(pdf, 0, 6, f"{i}. {step}")
        pdf.ln(1)

    pdf.ln(2)
    pdf.set_font("Arial", "B", 13)
    mc(pdf, 0, 8, "Primeros pasos")
    pdf.set_font("Arial", "", 11)
    steps2 = [
        "Cargar el DXF de las piezas: boton \"Cargar DXF\". Las piezas quedan "
        "listadas con sus medidas y las lineas de color originales.",
        "Agregar las planchas disponibles (medidas y cantidad) o cargar el DXF "
        "de la chapa si corresponde.",
        "Revisar el ancho de hoja (kerf) y la separacion por color de linea "
        "(por ejemplo, los ingletes en rojo).",
        "Pulsar \"Optimizar corte\". El calculo puede tardar unos minutos; la "
        "pagina muestra el progreso.",
        "Con el boton \"Exportar DXF\" se genera el plano optimizado con las "
        "piezas ubicadas, listo para la maquina de corte. En la app de "
        "escritorio el archivo se guarda en la carpeta data\\exportados, junto "
        "al programa; en la version web se descarga.",
    ]
    for i, step in enumerate(steps2, start=1):
        mc(pdf, 0, 6, f"{i}. {step}")
        pdf.ln(1)

    pdf.ln(2)
    pdf.set_font("Arial", "B", 13)
    mc(pdf, 0, 8, "Licencia y periodo de prueba")
    pdf.set_font("Arial", "", 11)
    mc(pdf, 0, 6,
        "La aplicacion incluye un periodo de prueba gratuito de 30 dias desde "
        "la primera ejecucion. El tiempo restante se muestra en la esquina "
        "superior derecha de la ventana.\n\n"
        "Cuando la prueba termina, la aplicacion pide una clave de activacion. "
        "Para obtenerla, comunicarse con el proveedor, indicando el nombre con "
        "el que se quiere registrar la licencia.\n\n"
        "Como activar:\n"
        "1. Copiar la clave recibida (formato XXXX-XXXX-XXXX-XXXX).\n"
        "2. Pegarla en el campo de la pantalla de licencia.\n"
        "3. Pulsar \"Activar licencia\".\n\n"
        "La clave queda guardada junto a la aplicacion: solo funciona en esa "
        "computadora con esa instalacion.")

    pdf.ln(2)
    pdf.set_font("Arial", "B", 13)
    mc(pdf, 0, 8, "Notas")
    pdf.set_font("Arial", "", 11)
    mc(pdf, 0, 6,
        "Los trabajos guardados se almacenan en una carpeta \"data\" que se "
        "crea junto al ejecutable. Para hacer una copia de seguridad basta con "
        "copiar esa carpeta.\n\n"
        "Si el programa no abre por el bloqueo de Windows, desmarcar en las "
        "propiedades del archivo la opcion \"Desbloquear\" (Propiedades, "
        "General, Desbloquear).\n\n"
        "Version 1.0 - Aresa-Nest")
    pdf.output("Guia_Instalacion_LaPuntualMarmoleria.pdf")
    print("PDF generado")


if __name__ == "__main__":
    build()
