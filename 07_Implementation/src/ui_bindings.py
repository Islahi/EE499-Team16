"""Restore QComboBox item identifiers from Qt Designer XML with their exact types.

QUiLoader can display item labels but drop the ``userData`` role.
Settings use string identifiers for operating modes and integer identifiers
for the Sindi 24/48/72-hour scheduling horizon.  Restoring everything as
strings (or ignoring <number> nodes) causes incorrect settings validation.
"""

from pathlib import Path
from xml.etree import ElementTree as ET


def _read_user_data(property_node: ET.Element | None):
    """Parse the supported Qt Designer scalar variant types without guessing."""
    if property_node is None:
        return None
    children = list(property_node)
    if len(children) != 1:
        raise ValueError("Combo userData must contain exactly one scalar value")
    child = children[0]
    if child.text is None:
        raise ValueError("Combo userData may not be empty")
    raw = child.text.strip()
    if child.tag == "string":
        if not raw:
            raise ValueError("Combo userData string may not be empty")
        return child.text
    if child.tag in ("number", "int", "uint"):
        return int(raw)
    if child.tag == "double":
        return float(raw)
    if child.tag == "bool":
        if raw.lower() not in ("true", "false"):
            raise ValueError(f"Invalid Qt boolean userData: {raw!r}")
        return raw.lower() == "true"
    raise ValueError(f"Unsupported Qt userData element: {child.tag!r}")


def read_designer_combo_data(ui_path: str | Path) -> dict[str, list[tuple[str, object]]]:
    """Return (visible label, typed semantic value) pairs for designer combos."""
    root = ET.parse(str(ui_path)).getroot()
    result = {}
    for combo in root.findall('.//widget[@class="QComboBox"]'):
        name = combo.attrib['name']
        items = combo.findall('item')
        if not items:
            continue
        declared = []
        has_userdata = False
        for item in items:
            text_prop = item.find('./property[@name="text"]/string')
            data_prop = item.find('./property[@name="userData"]')
            has_userdata = has_userdata or data_prop is not None
            label = text_prop.text if text_prop is not None else None
            value = _read_user_data(data_prop)
            declared.append((label, value))
        if not has_userdata:
            continue
        if any(label is None or value is None for label, value in declared):
            raise ValueError(f"{ui_path}: {name} has missing item label or userData entries")
        result[name] = [(str(label), value) for label, value in declared]
    return result


def restore_designer_combo_data(ui_path: str | Path, find_combo) -> None:
    """Restore QUiLoader's missing item data without altering layout or labels."""
    for name, declared in read_designer_combo_data(ui_path).items():
        combo = find_combo(name)
        if combo is None:
            raise RuntimeError(f"Designer combo {name!r} was not loaded")
        if combo.count() != len(declared):
            raise RuntimeError(f"Designer combo {name!r} has {combo.count()} entries; expected {len(declared)}")
        for index, (label, value) in enumerate(declared):
            if combo.itemText(index) != label:
                raise RuntimeError(
                    f"Designer combo {name!r} entry {index} changed: "
                    f"expected {label!r}, got {combo.itemText(index)!r}"
                )
            combo.setItemData(index, value)
            if combo.itemData(index) != value or type(combo.itemData(index)) is not type(value):
                raise RuntimeError(f"Cannot bind typed Designer value for {name!r} at index {index}")
