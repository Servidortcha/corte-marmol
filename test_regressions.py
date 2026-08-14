import io
import unittest

import ezdxf

from app import run_optimize
from core.dxf_io import export_result_dxf, parse_dxf_bytes
from core.models import OptimizeRequest


class RegressionTests(unittest.TestCase):
    def test_mixed_rectangles_and_polygons_are_all_placed(self):
        request = OptimizeRequest(
            pieces=[
                {"name": "Rectangulo", "width": 100, "height": 50},
                {
                    "name": "L",
                    "width": 100,
                    "height": 100,
                    "polygon": [[0, 0], [100, 0], [100, 40], [40, 40],
                                [40, 100], [0, 100]],
                },
            ],
            slabs=[{"name": "Plancha", "width": 500, "height": 500}],
        )

        result = run_optimize(request)

        self.assertEqual(result["total_pieces"], 2)
        self.assertEqual(result["pieces_placed"], 2)

    def test_exported_slabs_are_not_imported_as_pieces(self):
        result = {
            "slabs_used": [{
                "name": "Plancha",
                "width": 500,
                "height": 500,
                "pieces": [{
                    "name": "Pieza",
                    "width": 100,
                    "height": 50,
                    "x": 0,
                    "y": 0,
                    "rotated": False,
                }],
            }],
        }

        exported = export_result_dxf(result["slabs_used"])
        parsed = parse_dxf_bytes(exported)

        self.assertEqual(parsed["stats"]["piece_count"], 1)
        self.assertEqual(parsed["pieces"][0]["name"], "PIEZAS 1")

    def test_inches_are_converted_to_millimeters(self):
        doc = ezdxf.new("R2010")
        doc.header["$INSUNITS"] = 1
        doc.modelspace().add_lwpolyline(
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            close=True,
            dxfattribs={"layer": "PIEZA"},
        )
        output = io.StringIO()
        doc.write(output)

        parsed = parse_dxf_bytes(output.getvalue().encode("utf-8"))

        self.assertAlmostEqual(parsed["pieces"][0]["width"], 25.4, places=3)
        self.assertAlmostEqual(parsed["pieces"][0]["height"], 25.4, places=3)

    def test_colored_lines_are_preserved_in_export(self):
        doc = ezdxf.new("R2010")
        doc.header["$INSUNITS"] = 0
        msp = doc.modelspace()
        doc.layers.add("NEGRO", color=7)
        doc.layers.add("ROJO", color=1)
        msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "NEGRO"})
        msp.add_line((100, 0), (100, 50), dxfattribs={"layer": "NEGRO"})
        msp.add_line((100, 50), (0, 50), dxfattribs={"layer": "ROJO"})
        msp.add_line((0, 50), (0, 0), dxfattribs={"layer": "ROJO"})
        output = io.StringIO()
        doc.write(output)

        parsed = parse_dxf_bytes(output.getvalue().encode("utf-8"))

        self.assertEqual(len(parsed["pieces"]), 1)
        layers = {segment[0] for segment in parsed["pieces"][0].get("lines", [])}
        self.assertEqual(layers, {"NEGRO", "ROJO"})
        self.assertEqual(parsed["stats"]["layers_colors"].get("ROJO"), 1)

        exported = export_result_dxf(
            [{
                "name": "Plancha", "width": 200, "height": 200,
                "pieces": [{
                    "name": "Pieza 1", "width": 100, "height": 50,
                    "x": 10, "y": 10, "rotated": False,
                    "lines": parsed["pieces"][0]["lines"],
                }],
            }],
            layer_colors=parsed["stats"]["layers_colors"],
        )

        text = exported.decode("utf-8", errors="replace")
        self.assertIn("ROJO", text)
        self.assertIn("NEGRO", text)

    def test_custom_edge_distance_is_respected(self):
        import shapely.geometry as sg

        from core.packing import optimize_polygons

        pieces = [
            {
                "name": "A", "width": 100, "height": 50, "quantity": 1,
                "polygon": [[0, 0], [100, 0], [100, 50], [0, 50]],
                "lines": [["ROJO", 0, 0, 0, 50]],
            },
            {
                "name": "B", "width": 100, "height": 50, "quantity": 1,
                "polygon": [[0, 0], [100, 0], [100, 50], [0, 50]],
            },
        ]
        result = optimize_polygons(
            pieces,
            [{"name": "Plancha", "width": 220, "height": 100, "quantity": 1}],
            kerf=4,
            edge_distances={"ROJO": 10},
        )

        self.assertEqual(result["pieces_placed"], 2)
        slab = result["slabs_used"][0]
        geometries = [
            sg.Polygon([(x + p["x"], y + p["y"]) for x, y in p["polygon"]])
            for p in slab["pieces"]
        ]
        self.assertGreaterEqual(geometries[0].distance(geometries[1]), 9.9)

    def test_priority_orders_pieces_in_result(self):
        from core.packing import optimize

        result = optimize(
            [
                {"name": "Normal", "width": 200, "height": 100, "quantity": 1,
                 "priority": 0},
                {"name": "Urgente", "width": 150, "height": 80, "quantity": 1,
                 "priority": 1},
                {"name": "Media", "width": 120, "height": 60, "quantity": 1,
                 "priority": 2},
            ],
            [{"name": "Plancha", "width": 1000, "height": 500, "quantity": 1}],
            kerf=4,
        )

        self.assertEqual(result["pieces_placed"], 3)
        pieces = result["slabs_used"][0]["pieces"]
        priorities = [p["priority"] for p in pieces]
        self.assertEqual([p for p in priorities if p > 0],
                         sorted([p for p in priorities if p > 0]))
        self.assertEqual(pieces[0]["name"], "Urgente")
        self.assertEqual(pieces[1]["name"], "Media")

    def test_license_key_roundtrip(self):
        from core import licencia

        key = licencia.generate_key("Taller Prueba", days=30)
        info = licencia.validate_key(key)
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "Taller Prueba")
        tampered = key[:-4] + "AAAA"
        self.assertIsNone(licencia.validate_key(tampered))

    def test_trial_and_activation(self):
        import os
        import tempfile

        from core import licencia

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "licencia.json")
            os.environ["CORTE_LICENCIA_PATH"] = path
            try:
                licencia.reset_trial()
                estado = licencia.status()
                self.assertEqual(estado["status"], "trial")
                self.assertGreater(estado["days_left"], 0)
                key = licencia.generate_key("Cliente X", days=30)
                ok, _ = licencia.activate(key)
                self.assertTrue(ok)
                estado = licencia.status()
                self.assertEqual(estado["status"], "licensed")
                self.assertEqual(estado["licensed_to"], "Cliente X")
                self.assertFalse(licencia.activate("AAAA-BBBB-CCCC-DDDD")[0])
            finally:
                os.environ.pop("CORTE_LICENCIA_PATH", None)

    def test_pieces_do_not_enter_another_piece_holes(self):
        request = OptimizeRequest(
            pieces=[
                {
                    "name": "Marco",
                    "width": 400,
                    "height": 400,
                    "polygon": [[0, 0], [400, 0], [400, 400], [0, 400]],
                    "holes": [[[100, 100], [300, 100], [300, 300], [100, 300]]],
                },
                {
                    "name": "Relleno",
                    "width": 180,
                    "height": 180,
                },
            ],
            slabs=[{"name": "Plancha", "width": 600, "height": 600}],
        )

        result = run_optimize(request)

        self.assertEqual(result["pieces_placed"], 2)
        self.assertTrue(result["validation"]["valid"])
        marco = next(
            piece for slab in result["slabs_used"]
            for piece in slab["pieces"]
            if piece["name"] == "Marco"
        )
        nested = next(
            piece for slab in result["slabs_used"]
            for piece in slab["pieces"]
            if piece["name"] == "Relleno"
        )
        hole = marco["holes"][0]
        hx = [point[0] for point in hole]
        hy = [point[1] for point in hole]
        hole_minx = marco["x"] + min(hx)
        hole_maxx = marco["x"] + max(hx)
        hole_miny = marco["y"] + min(hy)
        hole_maxy = marco["y"] + max(hy)
        overlaps_hole = not (
            nested["x"] + nested["width"] <= hole_minx or
            nested["x"] >= hole_maxx or
            nested["y"] + nested["height"] <= hole_miny or
            nested["y"] >= hole_maxy
        )
        self.assertFalse(overlaps_hole)


if __name__ == "__main__":
    unittest.main()
