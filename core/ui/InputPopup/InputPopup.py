import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import os
import math
import base64
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFrame, QTextEdit, QLabel, QWidget,
    QVBoxLayout, QHBoxLayout, QSizePolicy
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QParallelAnimationGroup,
    QSequentialAnimationGroup, QEasingCurve, QPoint, QRect, QRectF,
    QPointF, pyqtProperty, QAbstractAnimation, QSize, qInstallMessageHandler
)
from PyQt5.QtGui import (
    QColor, QPainter, QLinearGradient, QRadialGradient, QPainterPath,
    QPen, QFontDatabase, QFont, QPixmap, QPalette
)


def _input_qt_message_handler(mode, context, message):
    suppressed = (
        "OpenType support missing",
        "QColor",
        "Unable to set geometry",
        "Resulting geometry",
        "QWindowsWindow::setGeometry",
    )
    if any(s in message for s in suppressed):
        return


qInstallMessageHandler(_input_qt_message_handler)


class GlassContainer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rgb = [191.0, 90.0, 242.0]
        self.phase = 0.0
        self._pulse = 0.0
        self.corner_radius = 28.0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(0, 0)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def update_visuals(self, rgb, phase):
        self.rgb = rgb
        self.phase = phase
        self.update()

    @pyqtProperty(float)
    def pulseIntensity(self):
        return self._pulse

    @pulseIntensity.setter
    def pulseIntensity(self, val):
        self._pulse = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect())
        r, g, b = [max(0, min(255, int(c))) for c in self.rgb]

        island_rect = rect.adjusted(5.0, 3.0, -5.0, -5.0)
        radius = self.corner_radius

        bg_grad = QLinearGradient(island_rect.topLeft(), island_rect.bottomLeft())
        bg_grad.setColorAt(0.0, QColor(31, 32, 42, 252))
        bg_grad.setColorAt(0.5, QColor(18, 19, 26, 254))
        bg_grad.setColorAt(1.0, QColor(9, 10, 15, 255))
        painter.setBrush(bg_grad)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(island_rect, radius, radius)

        ambient = QRadialGradient(
            QPointF(island_rect.left() + island_rect.width() * 0.22, island_rect.top()),
            island_rect.width() * 0.6
        )
        ambient.setColorAt(0.0, QColor(r, g, b, 36))
        ambient.setColorAt(0.55, QColor(r, g, b, 12))
        ambient.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(ambient)
        painter.drawRoundedRect(island_rect, radius, radius)

        bloom = QRadialGradient(
            QPointF(island_rect.center().x(), island_rect.bottom()),
            island_rect.width() * 0.55
        )
        bloom.setColorAt(0.0, QColor(r, g, b, 26))
        bloom.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(bloom)
        painter.drawRoundedRect(island_rect, radius, radius)

        cx = island_rect.center().x()
        cy = island_rect.center().y()
        span = max(island_rect.width(), island_rect.height()) * 0.7
        dx = math.cos(self.phase) * span
        dy = math.sin(self.phase) * span

        boost = int(self._pulse * 90)
        border_grad = QLinearGradient(
            QPointF(cx - dx, cy - dy),
            QPointF(cx + dx, cy + dy)
        )
        border_grad.setColorAt(0.0, QColor(255, 255, 255, min(255, 115 + boost // 2)))
        border_grad.setColorAt(0.35, QColor(255, 255, 255, 24))
        border_grad.setColorAt(0.72, QColor(r, g, b, min(255, 200 + boost // 3)))
        border_grad.setColorAt(1.0, QColor(255, 255, 255, 60))

        border_pen = QPen(border_grad, 1.35 + self._pulse * 0.35)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            island_rect.adjusted(0.7, 0.7, -0.7, -0.7),
            radius, radius
        )

        shine_rect = island_rect.adjusted(
            22.0, 1.2, -22.0, -(island_rect.height() - 2.0)
        )
        shine_grad = QLinearGradient(shine_rect.topLeft(), shine_rect.topRight())
        shine_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        shine_grad.setColorAt(0.5, QColor(255, 255, 255, 72))
        shine_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(shine_grad)
        painter.drawRect(shine_rect)


class EnterIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.rgb = [191.0, 90.0, 242.0]
        self._opacity = 0.0

    @pyqtProperty(float)
    def indicatorOpacity(self):
        return self._opacity

    @indicatorOpacity.setter
    def indicatorOpacity(self, val):
        self._opacity = val
        self.update()

    def set_visuals(self, rgb):
        self.rgb = rgb
        self.update()

    def paintEvent(self, event):
        if self._opacity < 0.02:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        r, g, b = [max(0, min(255, int(c))) for c in self.rgb]
        alpha = int(self._opacity * 255)
        cx, cy = self.width() / 2.0, self.height() / 2.0

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(r, g, b, int(alpha * 0.15)))
        painter.drawEllipse(QPointF(cx, cy), 12.5, 12.5)

        painter.setBrush(QColor(r, g, b, int(alpha * 0.22)))
        painter.drawEllipse(QPointF(cx, cy), 10.0, 10.0)

        pen = QPen(QColor(255, 255, 255, alpha), 1.9,
                   Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        path = QPainterPath()
        path.moveTo(cx + 4.5, cy - 5.5)
        path.lineTo(cx + 4.5, cy + 3.5)
        path.lineTo(cx - 3.0, cy + 3.5)
        painter.drawPath(path)

        arrow = QPainterPath()
        arrow.moveTo(cx - 6.5, cy + 1.0)
        arrow.lineTo(cx - 3.5, cy + 3.5)
        arrow.lineTo(cx - 6.5, cy + 6.0)
        painter.drawPath(arrow)


class SmartInput(QTextEdit):
    def __init__(self, parent_popup, parent=None):
        super().__init__(parent)
        self.parent_popup = parent_popup
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptRichText(False)

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.parent_popup.triggerAccept()
        elif event.key() == Qt.Key_Escape:
            self.parent_popup.triggerReject()
        else:
            super().keyPressEvent(event)


class InputPopup(QDialog):
    WIDTH = 720
    OUTER_MARGINS = (14, 10, 14, 14)
    CONTAINER_MARGINS = (26, 18, 26, 18)
    CONTAINER_SPACING = 16
    WINDOW_BOTTOM_OFFSET = 160
    MIN_TEXT_HEIGHT = 30
    MAX_TEXT_HEIGHT = 180
    VERTICAL_OVERHEAD = 70
    GLOW_INTERVAL_MS = 36
    GLOW_PHASE_STEP = 0.045
    ENTRY_FADE_MS = 280
    ENTRY_SLIDE_MS = 360
    EXIT_FADE_MS = 260
    EXIT_SLIDE_MS = 300
    RESIZE_MS = 340
    PULSE_PERIOD_MS = 1200
    FOCUS_DELAY_MS = 150

    def __init__(self, parent=None):
        super().__init__(parent)

        self.isClosing = False
        self.isTypingMode = False
        self.commandText = ""
        self.resizeAnimGroup = None
        self.outAnimGroup = None

        self.gradient_phase = 0.0
        self.current_rgb = [191.0, 90.0, 242.0]
        self.target_rgb = [191.0, 90.0, 242.0]

        self._load_fonts()
        self.initUI()

        self.glow_timer = QTimer(self)
        self.glow_timer.timeout.connect(self.update_glow_effect)
        self.glow_timer.start(self.GLOW_INTERVAL_MS)

    def _load_fonts(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        eng_path = os.path.join(base_dir, "Data", "fonts", "english.ttf")
        hin_path = os.path.join(base_dir, "Data", "fonts", "devangri.ttf")

        self.font_eng = QFont("Segoe UI", 13, QFont.Medium)
        eng_id = QFontDatabase.addApplicationFont(eng_path)
        if eng_id != -1:
            fams = QFontDatabase.applicationFontFamilies(eng_id)
            if fams:
                self.font_eng = QFont(fams[0], 13, QFont.Medium)

        self.font_hin = QFont("Nirmala UI", 14, QFont.Medium)
        hin_id = QFontDatabase.addApplicationFont(hin_path)
        if hin_id != -1:
            fams = QFontDatabase.applicationFontFamilies(hin_id)
            if fams:
                self.font_hin = QFont(fams[0], 14, QFont.Medium)

        fallback_chain = [self.font_hin.family(), "Nirmala UI",
                          "Segoe UI", "Mangal"]
        try:
            QFont.insertSubstitutions(self.font_eng.family(), fallback_chain)
            QFont.insertSubstitutions("MS Shell Dlg 2", fallback_chain)
            QFont.insertSubstitutions("Sansation", fallback_chain)
        except Exception:
            pass

        self.base_dir = base_dir

    def initUI(self):
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(self.WIDTH)

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(*self.OUTER_MARGINS)
        self.outer_layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)

        self.container = GlassContainer(self)
        self.container.setObjectName("Island")
        self.container.setMinimumSize(0, 0)

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(*self.CONTAINER_MARGINS)
        container_layout.setSpacing(self.CONTAINER_SPACING)
        container_layout.setAlignment(Qt.AlignTop)

        self.icon_label = QLabel(self.container)
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setAlignment(Qt.AlignCenter)

        icon_path = os.path.join(self.base_dir, "Data", "icons", "jarvis_icon.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.icon_label.setPixmap(pixmap.scaled(
                28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.icon_label.setStyleSheet(
                "background: transparent; border: none;"
            )
        else:
            self.icon_label.setText("J")
            self.icon_label.setFont(QFont(self.font_eng.family(), 18, QFont.Black))
            self.icon_label.setStyleSheet(
                "color: rgba(191, 90, 242, 0.95); "
                "background: transparent; border: none;"
            )

        container_layout.addWidget(self.icon_label, 0, Qt.AlignTop)

        self.inputField = SmartInput(self, self.container)
        self.inputField.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.inputField.setPlaceholderText("What do you need?")
        self.inputField.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: rgba(255, 255, 255, 0.98);
                border: none;
                font-family: "{self.font_eng.family()}", "{self.font_hin.family()}", "Segoe UI", sans-serif;
                font-size: 13.5pt;
                letter-spacing: 0.4px;
                selection-background-color: rgba(191, 90, 242, 0.45);
                selection-color: #FFFFFF;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.22);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(191, 90, 242, 0.65);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        try:
            pal = self.inputField.palette()
            pal.setColor(QPalette.PlaceholderText, QColor(255, 255, 255, 72))
            self.inputField.setPalette(pal)
        except AttributeError:
            pass

        container_layout.addWidget(self.inputField, 1)

        self.enter_indicator = EnterIndicator(self.container)
        self.enter_indicator.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        container_layout.addWidget(self.enter_indicator, 0, Qt.AlignTop)

        self.outer_layout.addWidget(self.container)
        self.inputField.textChanged.connect(self.onTextChanged)

        self.indicator_anim = QPropertyAnimation(
            self.enter_indicator, b"indicatorOpacity", self)
        self.indicator_anim.setDuration(400)
        self.indicator_anim.setEasingCurve(QEasingCurve.InOutSine)

        self.pulse_anim = QSequentialAnimationGroup(self)
        pulse_up = QPropertyAnimation(self.container, b"pulseIntensity")
        pulse_up.setDuration(self.PULSE_PERIOD_MS)
        pulse_up.setStartValue(0.0)
        pulse_up.setEndValue(1.0)
        pulse_up.setEasingCurve(QEasingCurve.InOutSine)
        pulse_down = QPropertyAnimation(self.container, b"pulseIntensity")
        pulse_down.setDuration(self.PULSE_PERIOD_MS)
        pulse_down.setStartValue(1.0)
        pulse_down.setEndValue(0.0)
        pulse_down.setEasingCurve(QEasingCurve.InOutSine)
        self.pulse_anim.addAnimation(pulse_up)
        self.pulse_anim.addAnimation(pulse_down)
        self.pulse_anim.setLoopCount(-1)

        self.setWindowOpacity(0.0)
        screen = QApplication.primaryScreen().availableGeometry()
        self.targetX = (screen.width() - self.width()) // 2
        self.baseBottomY = screen.height() - self.WINDOW_BOTTOM_OFFSET

        self.adjustHeight(False)

        self.entry_anim_group = QParallelAnimationGroup(self)
        fade_in = QPropertyAnimation(self, b"windowOpacity")
        fade_in.setDuration(self.ENTRY_FADE_MS)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)

        slide_up = QPropertyAnimation(self, b"pos")
        slide_up.setDuration(self.ENTRY_SLIDE_MS)
        slide_up.setStartValue(QPoint(self.targetX, self.y() + 28))
        slide_up.setEndValue(QPoint(self.targetX, self.y()))
        slide_up.setEasingCurve(QEasingCurve.OutQuint)

        self.entry_anim_group.addAnimation(fade_in)
        self.entry_anim_group.addAnimation(slide_up)
        self.entry_anim_group.start(QAbstractAnimation.DeleteWhenStopped)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(self.FOCUS_DELAY_MS, self.forceFocus)

    def closeEvent(self, event):
        if not self.isClosing:
            self.isClosing = True
            self.commandText = ""
            try:
                if self.glow_timer and self.glow_timer.isActive():
                    self.glow_timer.stop()
            except Exception:
                pass
            try:
                if self.pulse_anim and self.pulse_anim.state() == QAbstractAnimation.Running:
                    self.pulse_anim.stop()
            except Exception:
                pass
            try:
                if self.indicator_anim:
                    self.indicator_anim.stop()
            except Exception:
                pass
        event.accept()

    def update_glow_effect(self):
        self.gradient_phase += self.GLOW_PHASE_STEP
        if self.gradient_phase >= math.pi * 2:
            self.gradient_phase -= math.pi * 2

        for i in range(3):
            self.current_rgb[i] += (self.target_rgb[i] - self.current_rgb[i]) * 0.16

        self.container.update_visuals(self.current_rgb, self.gradient_phase)
        self.enter_indicator.set_visuals(self.current_rgb)

    def forceFocus(self):
        if self.isClosing:
            return
        try:
            self.activateWindow()
            self.raise_()
            self.inputField.setFocus()
        except Exception:
            pass

    def onTextChanged(self):
        text = self.inputField.toPlainText().strip()
        hasText = bool(text)

        if hasText != self.isTypingMode:
            self.isTypingMode = hasText

            if self.pulse_anim.state() == QAbstractAnimation.Running:
                self.pulse_anim.stop()
            self.container.pulseIntensity = 0.0

            self.indicator_anim.stop()
            self.indicator_anim.setStartValue(self.enter_indicator.indicatorOpacity)
            self.indicator_anim.setEndValue(0.95 if hasText else 0.0)
            self.indicator_anim.start()

            if hasText:
                self.target_rgb = [200.0, 100.0, 252.0]
                self.pulse_anim.start()
            else:
                self.target_rgb = [191.0, 90.0, 242.0]

        self.adjustHeight(True)

    def adjustHeight(self, animate):
        doc_height = int(self.inputField.document().size().height())
        new_text_height = max(self.MIN_TEXT_HEIGHT,
                              min(doc_height, self.MAX_TEXT_HEIGHT))

        if doc_height > self.MAX_TEXT_HEIGHT:
            self.inputField.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.inputField.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        new_window_height = new_text_height + self.VERTICAL_OVERHEAD

        if self.height() == new_window_height:
            return

        new_y = self.baseBottomY - new_window_height

        if animate and self.isVisible():
            if self.resizeAnimGroup is not None:
                if self.resizeAnimGroup.state() == QAbstractAnimation.Running:
                    self.resizeAnimGroup.stop()
                self.resizeAnimGroup.deleteLater()

            self.resizeAnimGroup = QParallelAnimationGroup(self)

            win_anim = QPropertyAnimation(self, b"geometry", self)
            win_anim.setDuration(self.RESIZE_MS)
            win_anim.setStartValue(self.geometry())
            win_anim.setEndValue(QRect(self.targetX, new_y,
                                       self.width(), new_window_height))
            win_anim.setEasingCurve(QEasingCurve.OutQuart)

            txt_min = QPropertyAnimation(self.inputField, b"minimumHeight", self)
            txt_min.setDuration(self.RESIZE_MS)
            txt_min.setStartValue(self.inputField.height())
            txt_min.setEndValue(new_text_height)
            txt_min.setEasingCurve(QEasingCurve.OutQuart)

            txt_max = QPropertyAnimation(self.inputField, b"maximumHeight", self)
            txt_max.setDuration(self.RESIZE_MS)
            txt_max.setStartValue(self.inputField.height())
            txt_max.setEndValue(new_text_height)
            txt_max.setEasingCurve(QEasingCurve.OutQuart)

            self.resizeAnimGroup.addAnimation(win_anim)
            self.resizeAnimGroup.addAnimation(txt_min)
            self.resizeAnimGroup.addAnimation(txt_max)
            self.resizeAnimGroup.start()
        else:
            self.inputField.setMinimumHeight(new_text_height)
            self.inputField.setMaximumHeight(new_text_height)
            self.setGeometry(self.targetX, new_y, self.width(), new_window_height)

    def triggerAccept(self):
        if self.isClosing:
            return
        self.isClosing = True
        self.commandText = self.inputField.toPlainText().strip()
        self.fadeOutAndClose(True)

    def triggerReject(self):
        if self.isClosing:
            return
        self.isClosing = True
        self.fadeOutAndClose(False)

    def fadeOutAndClose(self, is_accepting):
        if self.pulse_anim.state() == QAbstractAnimation.Running:
            self.pulse_anim.stop()
        self.indicator_anim.stop()
        self.glow_timer.stop()

        self.outAnimGroup = QParallelAnimationGroup(self)

        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(self.EXIT_FADE_MS)
        fade_out.setStartValue(self.windowOpacity())
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)

        slide_down = QPropertyAnimation(self, b"pos")
        slide_down.setDuration(self.EXIT_SLIDE_MS)
        slide_down.setStartValue(self.pos())
        slide_down.setEndValue(QPoint(self.x(), self.y() + 24))
        slide_down.setEasingCurve(QEasingCurve.InQuart)

        self.outAnimGroup.addAnimation(fade_out)
        self.outAnimGroup.addAnimation(slide_down)
        self.outAnimGroup.finished.connect(
            self.acceptDialog if is_accepting else self.rejectDialog
        )
        self.outAnimGroup.start()

    def acceptDialog(self):
        self.accept()

    def rejectDialog(self):
        self.reject()

    def getCommandText(self):
        return self.commandText


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        popup = InputPopup()
        popup.exec_()
        command = popup.getCommandText()
        if command:
            encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
            sys.stdout.write(f"JARVIS_CMD_B64:::{encoded}\n")
            sys.stdout.flush()
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        import traceback
        try:
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
        except Exception:
            pass
        sys.exit(1)