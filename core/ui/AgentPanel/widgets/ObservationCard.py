from PyQt5.QtCore import Qt, QRectF, QSize
from PyQt5.QtWidgets import QFrame
from PyQt5.QtGui import QPainter, QPen, QColor


class ObservationCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rgb = [191, 90, 242]
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(0, 0)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def set_accent(self, rgb):
        new_rgb = [max(0, min(255, int(c))) for c in rgb]
        if new_rgb != self.rgb:
            self.rgb = new_rgb
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        r, g, b = [max(0, min(255, int(c))) for c in self.rgb]

        painter.setBrush(QColor(255, 255, 255, 12))
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1.0))
        painter.drawRoundedRect(rect, 12.0, 12.0)

        bar_rect = QRectF(rect.left() + 5.0, rect.top() + 7.0, 3.2, max(6.0, rect.height() - 14.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(r, g, b, 220))
        painter.drawRoundedRect(bar_rect, 1.6, 1.6)