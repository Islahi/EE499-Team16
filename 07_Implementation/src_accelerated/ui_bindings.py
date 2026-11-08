"""Bind application values declared on QComboBox entries in Qt Designer files.

QUiLoader does not reliably restore item-level ``userData`` from .ui XML.
The visual layout and semantic identifiers stay in Designer; this adapter
restores each identifier into Qt.UserRole immediately after QUiLoader loads it.
No dependency on PySide6 is required to unit-test this bridge.
"""

from pathlib import Path
from xml.etree import ElementTree as ET


def read_designer_combo_data(ui_path: str | Path) -> dict[str, list[tuple[str, str]]]:
    """Return the declared (visible label, semantic ID) pairs for each combo.

    A combo with any userData fields must declare one for every item.
    This catches incomplete Designer edits instead of silently selecting None.
    """
    root = ET.parse(str(ui_path)).getroot()
    result = {}
    for combo in root.findall('.//widget[@class="QComboBox"]'):
        name = combo.attrib['name']
        declared = []
        items = combo.findall('item')
        if not items:
            continue
        for item in items:
            text_prop = item.find('./property[@name="text"]/string')
            data_prop = item.find('./property[@name="userData"]/string')
            label = text_prop.text if text_prop is not None else None
            value = data_prop.text if data_prop is not None else None
            declared.append((label, value))
        if all(value is None for _, value in declared):
            continue
        if any(value is None or not str(value).strip() for _, value in declared):
            raise ValueError(f"{ui_path}: {name} has missing userData entries")
        result[name] = [(str(label), str(value)) for label, value in declared]
    return result


def restore_designer_combo_data(ui_path: str | Path, find_combo) -> None:
    """Repair QUiLoader's missing item data without changing visual layout.

    ``find_combo(name)`` returns a QComboBox-like object. The explicit check
    against visible labels prevents a changed item order from misrouting data.
    """
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
            if combo.itemData(index) != value:
                raise RuntimeError(f"Cannot bind Designer value for {name!r} at index {index}")
