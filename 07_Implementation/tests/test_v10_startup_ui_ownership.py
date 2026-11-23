"""No-PySide6 static guard against misrouted Qt Designer widget access."""
import ast
import unittest
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "ui.py"
ASSETS = ROOT / "src" / "assets"
FORMS = {
    "LoadDataDialog": "load_data_dialog.ui",
    "SettingsDialog": "settings_dialog.ui",
    "SimulationInputDialog": "simulation_input_dialog.ui",
}


def direct_references(method_call):
    """Names looked up on self (not another dialog instance)."""
    args = method_call.args
    if not args or not isinstance(args[0], ast.Name) or args[0].id != "self":
        return []
    if not isinstance(method_call.func, ast.Name):
        return []
    name = method_call.func.id
    if name in ("widget", "hide_control_row") and len(args) >= 2:
        if isinstance(args[1], ast.Constant) and isinstance(args[1].value, str):
            return [(method_call.lineno, args[1].value)]
    if name == "hide_controls" and len(args) >= 2 and isinstance(args[1], (ast.Tuple, ast.List)):
        return [(method_call.lineno, x.value) for x in args[1].elts
                if isinstance(x, ast.Constant) and isinstance(x.value, str)]
    return []


class DesignerOwnershipTests(unittest.TestCase):
    def test_each_dialog_references_only_its_own_designer_controls(self):
        tree = ast.parse(SRC.read_text(encoding="utf-8"))
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        for class_name, filename in FORMS.items():
            with self.subTest(dialog=class_name):
                designer = ElementTree.parse(ASSETS / filename)
                available = {node.attrib["name"] for node in designer.iter()
                             if node.tag == "widget" and "name" in node.attrib}
                referenced = [ref for call in ast.walk(classes[class_name])
                              if isinstance(call, ast.Call)
                              for ref in direct_references(call)]
                missing = [(line, name) for line, name in referenced if name not in available]
                self.assertFalse(missing, f"{class_name} refers to controls in another form: {missing}")


    def test_legacy_voltage_percentage_has_no_desktop_control(self):
        asset = ElementTree.parse(ASSETS / FORMS["SettingsDialog"])
        self.assertIsNone(asset.find(".//widget[@name='spin_min_lateral_voltage_pct']"))


if __name__ == "__main__":
    unittest.main()
