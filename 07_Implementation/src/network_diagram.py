"""Selectable single-line graphics with independent input/result annotations."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView

from .network_layout import build_layout


class NetworkView(QGraphicsView):
    """Wheel zoom and a screen-sized hit corridor for thin feeder lines."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_press_handled = False

    def zoom_by(self, factor, position=None):
        if self.scene() is None or not self.scene().items():
            return
        current = self.transform().m11()
        target = max(min(0.01, current), min(20.0, current * factor))
        if position is None:
            position = self.viewport().rect().center()
        before = self.mapToScene(position)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.scale(target / current, target / current)
        after = self.mapToScene(position)
        self.translate(after.x() - before.x(), after.y() - before.y())

    def wheelEvent(self, event):
        if self.scene() is None or not self.scene().items():
            event.ignore()
            return
        delta = event.angleDelta().y()
        if not delta:
            delta = event.pixelDelta().y()
        if delta:
            self.zoom_by(1.25 ** (max(-1200, min(1200, delta)) / 120), event.position().toPoint())
        event.accept()

    def mousePressEvent(self, event):
        self.line_press_handled = False
        if event.button() == Qt.MouseButton.LeftButton and isinstance(self.scene(), NetworkScene):
            # Visible bus equipment/numbers win near a shared connection point.
            items = self.items(event.position().toPoint())
            bus_hit = any(item.data(1) in ("busbar", "load", "pv", "bess", "grid", "bus_number")
                          for item in items)
            if not bus_hit:
                label = next((item for item in items if item.data(1) == "line_id"), None)
                if label is not None:
                    self.scene().clearSelection()
                    self.scene().line_items[label.data(2)].setSelected(True)
                    self.line_press_handled = True
                    event.accept()
                    return
                stroker = QPainterPathStroker()
                stroker.setWidth(14)
                for line in self.scene().line_items.values():
                    path = self.mapFromScene(line.mapToScene(line.path()))
                    if stroker.createStroke(path).contains(event.position()):
                        self.scene().clearSelection()
                        line.setSelected(True)
                        self.line_press_handled = True
                        event.accept()
                        return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.line_press_handled and event.button() == Qt.MouseButton.LeftButton:
            # No default press was sent: its hand-drag release must not clear
            # the line selected through our wider hit corridor.
            self.line_press_handled = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class NetworkLine(QGraphicsPathItem):
    """Highlight the selected conductor itself, not its whole bounding box."""
    def paint(self, painter, option, widget=None):
        pen = QPen(self.pen())
        if self.isSelected():
            pen.setColor(QColor("#CC6413"))
            pen.setWidthF(3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())


class NetworkScene(QGraphicsScene):
    bus_selected = Signal(int)
    line_selected = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.bus_items = {}
        self.line_items = {}
        self.layout = None
        self.turns = 0
        self.branch_sides = {}
        self.selectionChanged.connect(self.select_element)

    def select_element(self):
        selected = self.selectedItems()
        if selected:
            item = selected[0]
            if item.data(1) == "bus":
                self.bus_selected.emit(item.data(0))
            elif item.data(1) == "line":
                self.line_selected.emit(item.data(2))

    def rotate_point(self, x, y):
        for _ in range(self.turns % 4):
            x, y = -y, x
        return x, y

    def add_symbol(self, group, path, role, tooltip, color="#173E50", fill=None):
        item = self.addPath(path, QPen(QColor(color), 2),
                            QBrush(QColor(fill)) if fill else QBrush())
        item.setParentItem(group)
        item.setData(1, role)
        item.setToolTip(tooltip)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        return item

    def add_label(self, group, text, x, y, role="label"):
        label = self.addSimpleText(text)
        font = label.font()
        font.setPointSizeF(18)
        label.setFont(font)
        if group is not None:
            label.setParentItem(group)
            label.setRotation(-90 * self.turns)
        label.setPos(x, y)
        label.setData(1, role)
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        return label

    def equipment(self, node, kind, port, left=False):
        sign = -1 if left else 1
        path = QPainterPath()
        path.moveTo(0, port)
        path.lineTo(sign * 90, port)
        if kind == "load":
            path.moveTo(sign * 90, port - 10)
            path.lineTo(sign * 90, port + 10)
            path.lineTo(sign * 110, port)
            path.closeSubpath()
            tooltip = "Aggregate connected load; not branch-flow direction"
        elif kind == "pv":
            path.addRect(sign * 90 if not left else -124, port - 20, 34, 40)
            path.moveTo(sign * 90, port - 20)
            path.lineTo(sign * 107, port - 4)
            path.lineTo(sign * 124, port - 20)
            path.moveTo(sign * 107, port - 4)
            path.lineTo(sign * 107, port + 20)
            tooltip = "Installed solar PV; aggregate AC connection"
        else:
            path.addRect(90 if not left else -128, port - 20, 38, 40)
            path.moveTo(sign * 105, port - 12)
            path.lineTo(sign * 105, port + 12)
            path.moveTo(sign * 114, port - 6)
            path.lineTo(sign * 114, port + 6)
            tooltip = "BESS installation; positive calculated power means discharge"
        self.add_symbol(node, path, kind, tooltip)
        if kind != "load":
            name = {"pv": "PV", "bess": "BESS"}[kind]
            self.add_label(node, name, -175 if left else 145, port - 8)

    def draw_network(self, network, voltages=None, bounds=(0.95, 1.05), bess_bus=None,
                     show_properties=False, step=None, bess_ratings=None):
        selected = next(((item.data(1), item.data(0) if item.data(1) == "bus" else item.data(2))
                         for item in self.selectedItems()), None)
        self.clear()
        self.bus_items.clear()
        self.line_items.clear()
        self.layout = build_layout(network, self.branch_sides,
                                   show_properties=show_properties, show_results=step is not None,
                                   bess_bus=bess_bus)
        good_result = step is not None and step.power_flow.converged
        if good_result:
            voltages = step.power_flow.voltage_mag_pu
        order = network.radial_order()
        parent_by_line = {line_id: order.parent_bus_by_bus[bus]
                          for bus, line_id in order.parent_line_by_bus.items()}
        for line in network.lines:
            points = self.layout.routes[line.line_id]
            path = QPainterPath()
            path.moveTo(*self.rotate_point(*points[0]))
            for point in points[1:]:
                path.lineTo(*self.rotate_point(*point))
            branch = NetworkLine(path)
            branch.setPen(QPen(QColor("#48758A"), 2))
            branch.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.addItem(branch)
            self.line_items[line.line_id] = branch
            branch.setData(1, "line")
            branch.setData(2, line.line_id)
            branch.setToolTip(f"{line.line_id}: {line.from_bus}–{line.to_bus}; result P/Q uses source-rooted sending end")
            # The longest segment provides room; short terminal stubs do not.
            a, b = max(zip(points, points[1:]),
                       key=lambda pair: abs(pair[1][0] - pair[0][0]) + abs(pair[1][1] - pair[0][1]))
            a, b = self.rotate_point(*a), self.rotate_point(*b)
            x, y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            horizontal = abs(a[1] - b[1]) < 1e-6
            label = self.add_label(None, line.line_id, x - 30 if horizontal else x - 90, y - 38, "line_id")
            label.setData(2, line.line_id)
            label.setToolTip(branch.toolTip())
            lines = []
            if show_properties:
                lines.append(f"R {line.r_ohm:g} Ω; X {line.x_ohm:g} Ω")
            if step is not None:
                if good_result:
                    flow = step.power_flow
                    lines.extend((f"P {flow.branch_p_kw[line.line_id]:.2f} kW; Q {flow.branch_q_kvar[line.line_id]:.2f} kvar",
                                  f"I {flow.branch_current_a[line.line_id]:.2f} A; loss {flow.line_loss_p_kw[line.line_id]:.3f} kW"))
                else:
                    lines.append("Result unavailable: power flow did not converge")
            if lines:
                label = self.add_label(None, "\n".join(lines), 0, 0, "line_annotation")
                rect = label.boundingRect()
                if horizontal and rect.width() > abs(b[0] - a[0]) - 80:
                    label.setText(label.text().replace("; ", "\n"))
                    rect = label.boundingRect()
                if horizontal:
                    parent = parent_by_line[line.line_id]
                    load_direction = -1 if self.layout.load_sides[parent] == "above" else 1
                    _, normal_y = self.rotate_point(0, load_direction)
                    above = normal_y >= 0
                    label.setPos(x - rect.width() / 2, y - rect.height() - 55 if above else y + 45)
                else:
                    label.setPos(x + 35, y - rect.height() / 2)
        for bus in network.buses:
            bus_id = bus.bus_id
            x, y = self.rotate_point(*self.layout.positions[bus_id])
            top, bottom = self.layout.bar_extents[bus_id]
            half = self.layout.bar_halves[bus_id]
            ports = self.layout.equipment_ports[bus_id]
            left_edge = -175 if bus.is_slack or any(left for _, _, left in ports) else -40
            named_equipment = any(kind != "load" and not left for kind, _, left in ports)
            right_edge = 250 if named_equipment else (130 if ports else 40)
            node = self.addRect(left_edge, top - 50, right_edge - left_edge, bottom - top + 100,
                                QPen(Qt.PenStyle.NoPen), QBrush(Qt.BrushStyle.NoBrush))
            node.setPos(x, y)
            node.setRotation(self.turns * 90)
            node.setData(0, bus_id)
            node.setData(1, "bus")
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.bus_items[bus_id] = node
            color = "#173E50"
            if voltages and bus_id in voltages:
                color = "#28713D" if bounds[0] <= voltages[bus_id] <= bounds[1] else "#B52B2B"
            bar = QPainterPath()
            bar.addRect(-3, top, 6, bottom - top)
            self.add_symbol(node, bar, "busbar", f"Bus {bus_id}; {bus.base_kv:g} kV", color, color)
            self.add_label(node, str(bus_id), -15, top - 36, "bus_number")
            loads = [load for load in network.loads if load.bus_id == bus_id]
            units = [unit for unit in network.pv_units if unit.bus_id == bus_id]
            for kind, port, left in self.layout.equipment_ports[bus_id]:
                self.equipment(node, kind, port, left=left)
            if bus.is_slack:
                grid = QPainterPath()
                grid.moveTo(0, 0)
                grid.lineTo(-100, 0)
                grid.addRect(-140, -20, 40, 40)
                for offset in (10, 20, 30):
                    grid.moveTo(-140 + offset, -20)
                    grid.lineTo(-140 + offset, 20)
                    grid.moveTo(-140, -20 + offset)
                    grid.lineTo(-100, -20 + offset)
                self.add_symbol(node, grid, "grid", "External grid / slack source")
                self.add_label(node, "Grid", -140, -50)
            node.setRect(node.rect().united(node.childrenBoundingRect()))
            inputs, outputs = [], []
            if show_properties:
                inputs = [f"Base {bus.base_kv:g} kV",
                          f"Load {sum(l.p_base_kw for l in loads):g} kW / {sum(l.q_base_kvar for l in loads):g} kvar",
                          f"PV rating {sum(u.p_rated_kw for u in units):g} kW"]
                if bus_id == bess_bus and bess_ratings is not None:
                    inputs.append(f"BESS {bess_ratings[0]:g} kW / {bess_ratings[1]:g} kWh")
            if step is not None:
                if good_result:
                    op = step.operating_point
                    outputs = [f"V {step.power_flow.voltage_mag_pu[bus_id]:.5f} pu",
                               f"Served load {op.p_load_kw[bus_id]:.2f} kW / {op.q_load_kvar[bus_id]:.2f} kvar",
                               f"PV {op.p_pv_kw[bus_id]:.2f} kW; BESS {op.p_bess_kw[bus_id]:.2f} kW"]
                    shed = step.shedding_by_bus_kw
                    curtailed = step.curtailment_by_bus_kw
                    shed_text = f"{shed[bus_id]:.2f}" if shed is not None and bus_id in shed else "N/A"
                    curt_text = f"{curtailed[bus_id]:.2f}" if curtailed is not None and bus_id in curtailed else "N/A"
                    outputs.append(f"Shed {shed_text} kW; curtailed {curt_text} kW")
                else:
                    outputs = ["Result unavailable: non-converged hour"]
            # Annotation text stays upright and outside the equipment envelope.
            if inputs:
                label = self.add_label(None, "\n".join(inputs), x + 80, y - 350, "bus_properties")
                if self.turns % 2:
                    label.setPos(x + half + 60, y - 150)
            if outputs:
                label = self.add_label(None, "\n".join(outputs), x - 140, y + 245, "bus_results")
                if self.turns % 2:
                    label.setPos(x - half - 60 - label.boundingRect().width(), y - 150)
            if selected == ("bus", bus_id):
                node.setSelected(True)
        if selected and selected[0] == "line" and selected[1] in self.line_items:
            self.line_items[selected[1]].setSelected(True)
        self.setSceneRect(self.itemsBoundingRect().adjusted(-40, -40, 40, 40))
