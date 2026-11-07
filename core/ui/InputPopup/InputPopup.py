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
import platform
import ctypes
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
    def __init__(self, initial_rgb=None, parent=None):
        super().__init__(parent)
        self.rgb = list(initial_rgb) if initial_rgb else [191.0, 90.0, 242.0]
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
        ambient.setColorAt(0.0, QColor(r, g, b, 38))
        ambient.setColorAt(0.55, QColor(r, g, b, 14))
        ambient.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(ambient)
        painter.drawRoundedRect(island_rect, radius, radius)

        bloom = QRadialGradient(
            QPointF(island_rect.center().x(), island_rect.bottom()),
            island_rect.width() * 0.55
        )
        bloom.setColorAt(0.0, QColor(r, g, b, 28))
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


class QuestionBanner(QFrame):
    def __init__(self, initial_rgb=None, parent=None):
        super().__init__(parent)
        self.rgb = list(initial_rgb) if initial_rgb else [56.0, 189.0, 248.0]
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_visuals(self, rgb):
        self.rgb = rgb
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect())
        r, g, b = [max(0, min(255, int(c))) for c in self.rgb]
        radius = 16.0

        bg_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        bg_grad.setColorAt(0.0, QColor(r, g, b, 24))
        bg_grad.setColorAt(0.6, QColor(255, 255, 255, 8))
        bg_grad.setColorAt(1.0, QColor(12, 14, 22, 160))
        painter.setBrush(bg_grad)

        border_pen = QPen(QColor(r, g, b, 75), 1.0)
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        bar_rect = QRectF(rect.left() + 1.0, rect.top() + 10.0, 3.2, max(12.0, rect.height() - 20.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(r, g, b, 230))
        painter.drawRoundedRect(bar_rect, 1.6, 1.6)


class EnterIndicator(QWidget):
    def __init__(self, initial_rgb=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.rgb = list(initial_rgb) if initial_rgb else [191.0, 90.0, 242.0]
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
    MIN_QUESTION_HEIGHT = 24
    MAX_QUESTION_HEIGHT = 135
    VERTICAL_OVERHEAD = 70
    GLOW_INTERVAL_MS = 36
    GLOW_PHASE_STEP = 0.045
    ENTRY_FADE_MS = 280
    ENTRY_SLIDE_MS = 360
    EXIT_FADE_MS = 260
    EXIT_SLIDE_MS = 300
    RESIZE_MS = 340
    PULSE_PERIOD_MS = 1200
    FOCUS_DELAY_MS = 120

    def __init__(self, question_text="", placeholder_text="", parent=None):
        super().__init__(parent)

        self.ask_question = (question_text or "").strip()
        self.ask_placeholder = (placeholder_text or "").strip()
        self.is_ask_mode = bool(self.ask_question)

        self.isClosing = False
        self.isTypingMode = False
        self.commandText = ""
        self.resizeAnimGroup = None
        self.outAnimGroup = None
        self.question_overhead = 0

        self.gradient_phase = 0.0
        if self.is_ask_mode:
            self.idle_rgb = [56.0, 189.0, 248.0]
            self.active_rgb = [103.0, 214.0, 255.0]
        else:
            self.idle_rgb = [191.0, 90.0, 242.0]
            self.active_rgb = [200.0, 100.0, 252.0]

        self.current_rgb = list(self.idle_rgb)
        self.target_rgb = list(self.idle_rgb)

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

        self.container = GlassContainer(self.current_rgb, self)
        self.container.setObjectName("Island")
        self.container.setMinimumSize(0, 0)

        container_vlayout = QVBoxLayout(self.container)
        container_vlayout.setContentsMargins(*self.CONTAINER_MARGINS)
        container_vlayout.setSpacing(12 if self.is_ask_mode else 0)

        self.question_banner = None
        self.question_view = None

        if self.is_ask_mode:
            self.question_banner = QuestionBanner(self.current_rgb, self.container)
            banner_layout = QVBoxLayout(self.question_banner)
            banner_layout.setContentsMargins(16, 10, 14, 10)
            banner_layout.setSpacing(4)

            badge_row = QHBoxLayout()
            badge_row.setContentsMargins(0, 0, 0, 0)
            badge_row.setSpacing(6)

            badge_dot = QLabel("●", self.question_banner)
            badge_dot.setStyleSheet(
                "color: rgba(56, 189, 248, 0.98); font-size: 9pt; background: transparent; border: none;"
            )
            badge_title = QLabel("JARVIS CLARIFICATION REQUEST", self.question_banner)
            badge_title.setStyleSheet(f"""
                color: rgba(125, 211, 252, 0.95);
                font-family: "{self.font_eng.family()}", "Segoe UI", sans-serif;
                font-size: 8.5pt;
                font-weight: 700;
                letter-spacing: 1.3px;
                background: transparent;
                border: none;
            """)
            badge_hint = QLabel("ESC to skip", self.question_banner)
            badge_hint.setStyleSheet(f"""
                color: rgba(255, 255, 255, 0.38);
                font-family: "{self.font_eng.family()}", "Segoe UI", sans-serif;
                font-size: 8pt;
                background: transparent;
                border: none;
            """)

            badge_row.addWidget(badge_dot, 0, Qt.AlignVCenter)
            badge_row.addWidget(badge_title, 0, Qt.AlignVCenter)
            badge_row.addStretch(1)
            badge_row.addWidget(badge_hint, 0, Qt.AlignVCenter)
            banner_layout.addLayout(badge_row)

            self.question_view = QTextEdit(self.question_banner)
            self.question_view.setReadOnly(True)
            self.question_view.setFrameShape(QFrame.NoFrame)
            self.question_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.question_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.question_view.setPlainText(self.ask_question)
            self.question_view.setStyleSheet(f"""
                QTextEdit {{
                    background: transparent;
                    color: rgba(241, 245, 249, 0.96);
                    border: none;
                    font-family: "{self.font_eng.family()}", "{self.font_hin.family()}", "Segoe UI", sans-serif;
                    font-size: 11.5pt;
                    selection-background-color: rgba(56, 189, 248, 0.38);
                    selection-color: #FFFFFF;
                }}
                QScrollBar:vertical {{
                    border: none;
                    background: transparent;
                    width: 5px;
                    margin: 0px;
                }}
                QScrollBar::handle:vertical {{
                    background: rgba(56, 189, 248, 0.35);
                    border-radius: 2px;
                    min-height: 16px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    height: 0px;
                }}
            """)
            banner_layout.addWidget(self.question_view)
            container_vlayout.addWidget(self.question_banner)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(self.CONTAINER_SPACING)
        input_row.setAlignment(Qt.AlignTop)

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
            accent_css = "rgba(56, 189, 248, 0.95)" if self.is_ask_mode else "rgba(191, 90, 242, 0.95)"
            self.icon_label.setStyleSheet(
                f"color: {accent_css}; background: transparent; border: none;"
            )

        input_row.addWidget(self.icon_label, 0, Qt.AlignTop)

        self.inputField = SmartInput(self, self.container)
        self.inputField.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        default_ph = "Type your answer for Jarvis..." if self.is_ask_mode else "What do you need?"
        self.inputField.setPlaceholderText(self.ask_placeholder or default_ph)
        sel_bg = "rgba(56, 189, 248, 0.42)" if self.is_ask_mode else "rgba(191, 90, 242, 0.45)"
        scroll_hover = "rgba(56, 189, 248, 0.65)" if self.is_ask_mode else "rgba(191, 90, 242, 0.65)"
        self.inputField.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: rgba(255, 255, 255, 0.98);
                border: none;
                font-family: "{self.font_eng.family()}", "{self.font_hin.family()}", "Segoe UI", sans-serif;
                font-size: 13.5pt;
                letter-spacing: 0.4px;
                selection-background-color: {sel_bg};
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
                background: {scroll_hover};
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
            pal.setColor(QPalette.PlaceholderText, QColor(255, 255, 255, 78))
            self.inputField.setPalette(pal)
        except AttributeError:
            pass

        input_row.addWidget(self.inputField, 1)

        self.enter_indicator = EnterIndicator(self.current_rgb, self.container)
        self.enter_indicator.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        input_row.addWidget(self.enter_indicator, 0, Qt.AlignTop)

        container_vlayout.addLayout(input_row)
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

        self._computeQuestionGeometry()
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

    def _computeQuestionGeometry(self):
        if not self.is_ask_mode or not self.question_view or not self.question_banner:
            self.question_overhead = 0
            return

        avail_width = (
            self.WIDTH
            - self.OUTER_MARGINS[0] - self.OUTER_MARGINS[2]
            - self.CONTAINER_MARGINS[0] - self.CONTAINER_MARGINS[2]
            - 30
        )
        self.question_view.document().setTextWidth(avail_width)
        q_doc_h = int(self.question_view.document().size().height()) + 4
        clamped_q_h = max(self.MIN_QUESTION_HEIGHT, min(q_doc_h, self.MAX_QUESTION_HEIGHT))

        if q_doc_h > self.MAX_QUESTION_HEIGHT:
            self.question_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.question_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.question_view.setFixedHeight(clamped_q_h)
        banner_h = clamped_q_h + 42
        self.question_banner.setFixedHeight(banner_h)
        self.question_overhead = banner_h + 12

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
        if self.question_banner is not None:
            self.question_banner.set_visuals(self.current_rgb)

    def forceFocus(self):
        if self.isClosing:
            return
        try:
            if platform.system() == "Windows":
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                fg_hwnd = user32.GetForegroundWindow()
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
                cur_tid = kernel32.GetCurrentThreadId()
                if fg_tid and fg_tid != cur_tid:
                    user32.AttachThreadInput(fg_tid, cur_tid, True)
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
                    user32.SetFocus(hwnd)
                    user32.AttachThreadInput(fg_tid, cur_tid, False)
                else:
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
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
                self.target_rgb = list(self.active_rgb)
                self.pulse_anim.start()
            else:
                self.target_rgb = list(self.idle_rgb)

        self.adjustHeight(True)

    def adjustHeight(self, animate):
        doc_height = int(self.inputField.document().size().height())
        new_text_height = max(self.MIN_TEXT_HEIGHT,
                              min(doc_height, self.MAX_TEXT_HEIGHT))

        if doc_height > self.MAX_TEXT_HEIGHT:
            self.inputField.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.inputField.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        new_window_height = new_text_height + self.VERTICAL_OVERHEAD + self.question_overhead

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
        raw = self.inputField.toPlainText().strip()
        if not raw and self.is_ask_mode:
            return
        self.isClosing = True
        self.commandText = raw
        self.fadeOutAndClose(True)

    def triggerReject(self):
        if self.isClosing:
            return
        self.isClosing = True
        self.commandText = ""
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
        question_env = os.environ.get("JARVIS_ASK_QUESTION", "").strip()
        placeholder_env = os.environ.get("JARVIS_ASK_PLACEHOLDER", "").strip()
        popup = InputPopup(
            question_text=question_env,
            placeholder_text=placeholder_env
        )
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