import io
import ezdxf

doc = ezdxf.new("R2010")
doc.units = ezdxf.units.MM
msp = doc.modelspace()
msp.add_lwpolyline([(0, 0), (600, 0), (600, 300), (300, 300), (300, 600), (0, 600)],
                   close=True, dxfattribs={"layer": "ESCALERA"})
msp.add_circle((1200, 800), radius=350, dxfattribs={"layer": "TAPA"})
msp.add_circle((1200, 800), radius=80, dxfattribs={"layer": "TAPA"})
buf = io.StringIO()
doc.write(buf)
with open("muestra.dxf", "w", encoding="utf-8") as f:
    f.write(buf.getvalue())
print("muestra.dxf escrito")
