"""Small palette-aware Qt vector icons; no external image downloads."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPen, QPixmap


def network_icon(action: str, palette: QPalette) -> QIcon:
    icon = QIcon()
    for mode, group in ((QIcon.Mode.Normal, QPalette.ColorGroup.Active),
                        (QIcon.Mode.Disabled, QPalette.ColorGroup.Disabled)):
        image = QPixmap(48, 48)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(2, 2)
        pen = QPen(palette.color(group, QPalette.ColorRole.ButtonText), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        if action == "fit":
            for x, y, dx, dy in ((4, 4, 1, 1), (20, 4, -1, 1),
                                 (4, 20, 1, -1), (20, 20, -1, -1)):
                painter.drawLine(QPointF(x, y), QPointF(x + dx * 5, y))
                painter.drawLine(QPointF(x, y), QPointF(x, y + dy * 5))
        else:
            painter.drawEllipse(QRectF(3, 3, 13, 13))
            painter.drawLine(QPointF(15, 15), QPointF(21, 21))
            painter.drawLine(QPointF(6, 9.5), QPointF(13, 9.5))
            if action == "zoom_in":
                painter.drawLine(QPointF(9.5, 6), QPointF(9.5, 13))
        painter.end()
        icon.addPixmap(image, mode)
    return icon
