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
    def __init__(self, initial_rgb=None, secondary_rgb=None, is_ask_mode=False, parent=None):
        super().__init__(parent)
        self.rgb = list(initial_rgb) if initial_rgb else [191.0, 90.0, 242.0]
        self.rgb2 = list(secondary_rgb) if secondary_rgb else [120.0, 115.0, 245.0]
        self.is_ask_mode = is_ask_mode
        self.phase = 0.0
        self._pulse = 0.0
        self.error_flash = 0.0
        self.header_bottom_y = 0.0
        self.corner_radius = 26.0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(0, 0)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def update_visuals(self, rgb, rgb2, phase, error_flash=0.0, header_bottom_y=0.0):
        self.rgb = rgb
        self.rgb2 = rgb2
        self.phase = phase
        self.error_flash = error_flash
        self.header_bottom_y = header_bottom_y
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
        ef = max(0.0, min(1.0, self.error_flash))

        r = int(max(0, min(255, self.rgb[0] * (1.0 - ef) + 255.0 * ef)))
        g = int(max(0, min(255, self.rgb[1] * (1.0 - ef) + 78.0 * ef)))
        b = int(max(0, min(255, self.rgb[2] * (1.0 - ef) + 98.0 * ef)))

        r2 = int(max(0, min(255, self.rgb2[0] * (1.0 - ef) + 255.0 * ef)))
        g2 = int(max(0, min(255, self.rgb2[1] * (1.0 - ef) + 120.0 * ef)))
        b2 = int(max(0, min(255, self.rgb2[2] * (1.0 - ef) + 80.0 * ef)))

        island_rect = rect.adjusted(8.0, 4.0, -8.0, -10.0)
        radius = self.corner_radius

        shadow_specs = (
            (1.0, 1.5, 28, 1.0),
            (2.5, 3.5, 22, 2.0),
            (4.5, 6.0, 14, 3.5),
            (7.0, 8.5, 8, 5.0),
        )
        painter.setPen(Qt.NoPen)
        for spread, dy, alpha, extra_r in shadow_specs:
            s_rect = island_rect.adjusted(-spread, dy - spread * 0.4, spread, dy + spread)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(s_rect, radius + extra_r * 0.4, radius + extra_r * 0.4)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(island_rect, radius, radius)
        painter.save()
        painter.setClipPath(clip_path)

        bg_grad = QLinearGradient(island_rect.topLeft(), island_rect.bottomLeft())
        bg_grad.setColorAt(0.0, QColor(24, 26, 36, 252))
        bg_grad.setColorAt(0.45, QColor(15, 16, 23, 254))
        bg_grad.setColorAt(1.0, QColor(9, 10, 15, 255))
        painter.setBrush(bg_grad)
        painter.drawRect(island_rect)

        if self.is_ask_mode and self.header_bottom_y > 0:
            header_rect = QRectF(
                island_rect.left(),
                island_rect.top(),
                island_rect.width(),
                min(island_rect.height(), self.header_bottom_y)
            )
            header_grad = QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
            header_grad.setColorAt(0.0, QColor(r, g, b, 22))
            header_grad.setColorAt(0.7, QColor(r2, g2, b2, 8))
            header_grad.setColorAt(1.0, QColor(255, 255, 255, 4))
            painter.setBrush(header_grad)
            painter.drawRect(header_rect)

        ambient_top = QRadialGradient(
            QPointF(island_rect.left() + island_rect.width() * 0.2, island_rect.top()),
            island_rect.width() * 0.65
        )
        ambient_top.setColorAt(0.0, QColor(r, g, b, int(34 + self._pulse * 16 + ef * 35)))
        ambient_top.setColorAt(0.55, QColor(r2, g2, b2, 12))
        ambient_top.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(ambient_top)
        painter.drawRect(island_rect)

        bloom_bottom = QRadialGradient(
            QPointF(island_rect.right() - island_rect.width() * 0.22, island_rect.bottom()),
            island_rect.width() * 0.55
        )
        bloom_bottom.setColorAt(0.0, QColor(r2, g2, b2, int(24 + self._pulse * 18)))
        bloom_bottom.setColorAt(1.0, QColor(r2, g2, b2, 0))
        painter.setBrush(bloom_bottom)
        painter.drawRect(island_rect)

        rim_rect = QRectF(island_rect.left(), island_rect.top(), island_rect.width(), 2.0)
        rim_grad = QLinearGradient(rim_rect.topLeft(), rim_rect.topRight())
        rim_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        rim_grad.setColorAt(0.2, QColor(255, 255, 255, 45))
        rim_grad.setColorAt(0.5, QColor(255, 255, 255, 95))
        rim_grad.setColorAt(0.8, QColor(255, 255, 255, 45))
        rim_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(rim_grad)
        painter.drawRect(rim_rect)

        painter.restore()

        cx = island_rect.center().x()
        cy = island_rect.center().y()
        span = max(island_rect.width(), island_rect.height()) * 0.72
        dx = math.cos(self.phase) * span
        dy = math.sin(self.phase) * span

        boost = int(self._pulse * 75 + ef * 90)
        border_grad = QLinearGradient(
            QPointF(cx - dx, cy - dy),
            QPointF(cx + dx, cy + dy)
        )
        border_grad.setColorAt(0.0, QColor(255, 255, 255, min(255, 95 + boost // 2)))
        border_grad.setColorAt(0.32, QColor(r, g, b, min(255, 165 + boost // 2)))
        border_grad.setColorAt(0.68, QColor(r2, g2, b2, min(255, 195 + boost // 2)))
        border_grad.setColorAt(1.0, QColor(255, 255, 255, 48))

        border_pen = QPen(border_grad, 1.25 + self._pulse * 0.35 + ef * 0.45)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            island_rect.adjusted(0.6, 0.6, -0.6, -0.6),
            radius, radius
        )


class RadarDot(QWidget):
    def __init__(self, initial_rgb=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.rgb = list(initial_rgb) if initial_rgb else [56.0, 189.0, 248.0]
        self.phase = 0.0

    def set_visuals(self, rgb, phase):
        self.rgb = rgb
        self.phase = phase
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        r, g, b = [max(0, min(255, int(c))) for c in self.rgb]
        cx, cy = self.width() / 2.0, self.height() / 2.0

        wave = (math.sin(self.phase * 1.6) + 1.0) * 0.5
        halo_radius = 4.2 + wave * 3.2
        halo_alpha = int(95 * (1.0 - wave * 0.65))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(r, g, b, halo_alpha))
        painter.drawEllipse(QPointF(cx, cy), halo_radius, halo_radius)

        painter.setBrush(QColor(r, g, b, 245))
        painter.drawEllipse(QPointF(cx, cy), 3.1, 3.1)

        painter.setBrush(QColor(255, 255, 255, 210))
        painter.drawEllipse(QPointF(cx - 0.6, cy - 0.6), 1.1, 1.1)


class KeycapHint(QWidget):
    def __init__(self, key_text="ESC", label_text="Skip", font_family="Segoe UI", on_click=None, parent=None):
        super().__init__(parent)
        self.key_text = key_text
        self.label_text = label_text
        self.font_family = font_family
        self.on_click = on_click
        self.hovered = False
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if on_click is not None:
            self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(20)
        self.setFixedWidth(68)

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and callable(self.on_click):
            self.on_click()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        bg_alpha = 38 if self.hovered else 22
        border_alpha = 85 if self.hovered else 48
        text_alpha = 215 if self.hovered else 145

        cap_rect = QRectF(1.0, 2.0, 29.0, 16.0)
        painter.setBrush(QColor(255, 255, 255, bg_alpha))
        painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1.0))
        painter.drawRoundedRect(cap_rect, 4.5, 4.5)

        key_font = QFont(self.font_family, 7, QFont.Bold)
        painter.setFont(key_font)
        painter.setPen(QColor(255, 255, 255, min(255, text_alpha + 25)))
        painter.drawText(cap_rect, Qt.AlignCenter, self.key_text)

        lbl_rect = QRectF(35.0, 2.0, self.width() - 36.0, 16.0)
        lbl_font = QFont(self.font_family, 8, QFont.Medium)
        painter.setFont(lbl_font)
        painter.setPen(QColor(255, 255, 255, text_alpha - 25))
        painter.drawText(lbl_rect, Qt.AlignLeft | Qt.AlignVCenter, self.label_text)


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

        y = rect.bottom() - 0.5
        line_grad = QLinearGradient(QPointF(rect.left(), y), QPointF(rect.right(), y))
        line_grad.setColorAt(0.0, QColor(r, g, b, 0))
        line_grad.setColorAt(0.18, QColor(r, g, b, 68))
        line_grad.setColorAt(0.5, QColor(255, 255, 255, 85))
        line_grad.setColorAt(0.82, QColor(r, g, b, 68))
        line_grad.setColorAt(1.0, QColor(r, g, b, 0))

        painter.setPen(QPen(line_grad, 1.0))
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))


class EnterIndicator(QWidget):
    def __init__(self, initial_rgb=None, on_click=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.rgb = list(initial_rgb) if initial_rgb else [191.0, 90.0, 242.0]
        self._opacity = 0.0
        self.on_click = on_click
        self.hovered = False

    @pyqtProperty(float)
    def indicatorOpacity(self):
        return self._opacity

    @indicatorOpacity.setter
    def indicatorOpacity(self, val):
        self._opacity = val
        if self._opacity > 0.15:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def set_visuals(self, rgb):
        self.rgb = rgb
        self.update()

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._opacity > 0.15 and callable(self.on_click):
            self.on_click()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        if self._opacity < 0.02:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        r, g, b = [max(0, min(255, int(c))) for c in self.rgb]
        alpha = int(self._opacity * 255)
        cx, cy = self.width() / 2.0, self.height() / 2.0

        hover_boost = 1.25 if self.hovered else 1.0
        pill_rect = QRectF(2.0, 2.0, self.width() - 4.0, self.height() - 4.0)

        bg_grad = QLinearGradient(pill_rect.topLeft(), pill_rect.bottomRight())
        bg_grad.setColorAt(0.0, QColor(r, g, b, min(255, int(alpha * 0.34 * hover_boost))))
        bg_grad.setColorAt(1.0, QColor(r, g, b, min(255, int(alpha * 0.18 * hover_boost))))

        painter.setBrush(bg_grad)
        painter.setPen(QPen(QColor(r, g, b, min(255, int(alpha * 0.55 * hover_boost))), 1.0))
        painter.drawRoundedRect(pill_rect, 8.5, 8.5)

        pen = QPen(QColor(255, 255, 255, alpha), 1.85,
                   Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        path = QPainterPath()
        path.moveTo(cx + 4.0, cy - 4.5)
        path.lineTo(cx + 4.0, cy + 2.5)
        path.lineTo(cx - 3.5, cy + 2.5)
        painter.drawPath(path)

        arrow = QPainterPath()
        arrow.moveTo(cx - 1.0, cy - 0.2)
        arrow.lineTo(cx - 4.0, cy + 2.5)
        arrow.lineTo(cx - 1.0, cy + 5.2)
        painter.drawPath(arrow)


class SmartInput(QTextEdit):
    def __init__(self, parent_popup, parent=None):
        super().__init__(parent)
        self.parent_popup = parent_popup
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptRichText(False)
        self.document().setDocumentMargin(0.0)
        self.setViewportMargins(0, 3, 0, 3)

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
    CONTAINER_SPACING = 14
    WINDOW_BOTTOM_OFFSET = 160
    MIN_TEXT_HEIGHT = 28
    MAX_TEXT_HEIGHT = 180
    MIN_QUESTION_HEIGHT = 22
    MAX_QUESTION_HEIGHT = 135
    VERTICAL_OVERHEAD = 68
    GLOW_INTERVAL_MS = 32
    GLOW_PHASE_STEP = 0.045
    ENTRY_FADE_MS = 260
    ENTRY_SLIDE_MS = 340
    EXIT_FADE_MS = 240
    EXIT_SLIDE_MS = 280
    RESIZE_MS = 300
    PULSE_PERIOD_MS = 1200
    FOCUS_DELAY_MS = 110

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
        self.shakeAnim = None
        self.question_overhead = 0
        self.error_flash = 0.0

        self.gradient_phase = 0.0
        if self.is_ask_mode:
            self.idle_rgb = [56.0, 189.0, 248.0]
            self.active_rgb = [96.0, 218.0, 255.0]
            self.idle_rgb2 = [99.0, 102.0, 241.0]
            self.active_rgb2 = [139.0, 92.0, 246.0]
        else:
            self.idle_rgb = [180.0, 86.0, 235.0]
            self.active_rgb = [216.0, 110.0, 255.0]
            self.idle_rgb2 = [99.0, 102.0, 241.0]
            self.active_rgb2 = [244.0, 114.0, 182.0]

        self.current_rgb = list(self.idle_rgb)
        self.target_rgb = list(self.idle_rgb)
        self.current_rgb2 = list(self.idle_rgb2)
        self.target_rgb2 = list(self.idle_rgb2)

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

        self.container = GlassContainer(
            self.current_rgb, self.current_rgb2, self.is_ask_mode, self
        )
        self.container.setObjectName("Island")
        self.container.setMinimumSize(0, 0)

        container_vlayout = QVBoxLayout(self.container)
        container_vlayout.setContentsMargins(*self.CONTAINER_MARGINS)
        container_vlayout.setSpacing(12 if self.is_ask_mode else 0)

        self.question_banner = None
        self.question_view = None
        self.radar_dot = None
        self.esc_badge = None

        if self.is_ask_mode:
            self.question_banner = QuestionBanner(self.current_rgb, self.container)
            banner_layout = QVBoxLayout(self.question_banner)
            banner_layout.setContentsMargins(2, 0, 2, 12)
            banner_layout.setSpacing(6)

            badge_row = QHBoxLayout()
            badge_row.setContentsMargins(0, 0, 0, 0)
            badge_row.setSpacing(8)

            self.radar_dot = RadarDot(self.current_rgb, self.question_banner)
            badge_title = QLabel("JARVIS  •  AWAITING INPUT", self.question_banner)
            badge_title.setStyleSheet(f"""
                color: rgba(125, 211, 252, 0.92);
                font-family: "{self.font_eng.family()}", "Segoe UI", sans-serif;
                font-size: 8pt;
                font-weight: 700;
                letter-spacing: 1.4px;
                background: transparent;
                border: none;
            """)
            self.esc_badge = KeycapHint(
                "ESC", "Skip", self.font_eng.family(),
                on_click=self.triggerReject, parent=self.question_banner
            )

            badge_row.addWidget(self.radar_dot, 0, Qt.AlignVCenter)
            badge_row.addWidget(badge_title, 0, Qt.AlignVCenter)
            badge_row.addStretch(1)
            badge_row.addWidget(self.esc_badge, 0, Qt.AlignVCenter)
            banner_layout.addLayout(badge_row)

            self.question_view = QTextEdit(self.question_banner)
            self.question_view.setReadOnly(True)
            self.question_view.setFrameShape(QFrame.NoFrame)
            self.question_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.question_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.question_view.document().setDocumentMargin(0.0)
            self.question_view.setPlainText(self.ask_question)
            self.question_view.setStyleSheet(f"""
                QTextEdit {{
                    background: transparent;
                    color: rgba(241, 245, 249, 0.95);
                    border: none;
                    font-family: "{self.font_eng.family()}", "{self.font_hin.family()}", "Segoe UI", sans-serif;
                    font-size: 11.5pt;
                    selection-background-color: rgba(56, 189, 248, 0.38);
                    selection-color: #FFFFFF;
                }}
                QScrollBar:vertical {{
                    border: none;
                    background: transparent;
                    width: 4px;
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

        self.icon_label = QLabel(self.container)
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setAlignment(Qt.AlignCenter)

        icon_path = os.path.join(self.base_dir, "Data", "icons", "jarvis_icon.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.icon_label.setPixmap(pixmap.scaled(
                26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.icon_label.setStyleSheet(
                "background: transparent; border: none;"
            )
        else:
            self.icon_label.setText("J")
            self.icon_label.setFont(QFont(self.font_eng.family(), 16, QFont.Black))
            accent_css = "rgba(56, 189, 248, 0.95)" if self.is_ask_mode else "rgba(191, 90, 242, 0.95)"
            self.icon_label.setStyleSheet(
                f"color: {accent_css}; background: transparent; border: none;"
            )

        input_row.addWidget(self.icon_label, 0, Qt.AlignTop)

        self.inputField = SmartInput(self, self.container)
        self.inputField.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        default_ph = "Type your response..." if self.is_ask_mode else "What do you need?"
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
                letter-spacing: 0.3px;
                selection-background-color: {sel_bg};
                selection-color: #FFFFFF;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 5px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.20);
                border-radius: 2px;
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
            pal.setColor(QPalette.PlaceholderText, QColor(255, 255, 255, 82))
            self.inputField.setPalette(pal)
        except AttributeError:
            pass

        input_row.addWidget(self.inputField, 1)

        self.enter_indicator = EnterIndicator(
            self.current_rgb, on_click=self.triggerAccept, parent=self.container
        )
        self.enter_indicator.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        input_row.addWidget(self.enter_indicator, 0, Qt.AlignBottom)

        container_vlayout.addLayout(input_row)
        self.outer_layout.addWidget(self.container)

        self.inputField.textChanged.connect(self.onTextChanged)

        self.indicator_anim = QPropertyAnimation(
            self.enter_indicator, b"indicatorOpacity", self)
        self.indicator_anim.setDuration(260)
        self.indicator_anim.setEasingCurve(QEasingCurve.OutCubic)

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
        slide_up.setStartValue(QPoint(self.targetX, self.y() + 24))
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
            - 8
        )
        self.question_view.document().setTextWidth(avail_width)
        q_doc_h = int(self.question_view.document().size().height()) + 2
        clamped_q_h = max(self.MIN_QUESTION_HEIGHT, min(q_doc_h, self.MAX_QUESTION_HEIGHT))

        if q_doc_h > self.MAX_QUESTION_HEIGHT:
            self.question_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.question_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.question_view.setFixedHeight(clamped_q_h)
        banner_h = clamped_q_h + 38
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

        if self.error_flash > 0.005:
            self.error_flash *= 0.84
        else:
            self.error_flash = 0.0

        for i in range(3):
            self.current_rgb[i] += (self.target_rgb[i] - self.current_rgb[i]) * 0.16
            self.current_rgb2[i] += (self.target_rgb2[i] - self.current_rgb2[i]) * 0.16

        header_bottom = 0.0
        if self.question_banner is not None:
            header_bottom = float(self.CONTAINER_MARGINS[1] + self.question_banner.height())
            self.question_banner.set_visuals(self.current_rgb)

        if self.radar_dot is not None:
            self.radar_dot.set_visuals(self.current_rgb, self.gradient_phase)

        self.container.update_visuals(
            self.current_rgb,
            self.current_rgb2,
            self.gradient_phase,
            self.error_flash,
            header_bottom
        )
        self.enter_indicator.set_visuals(self.current_rgb)

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
            self.indicator_anim.setEndValue(0.98 if hasText else 0.0)
            self.indicator_anim.start()

            if hasText:
                self.target_rgb = list(self.active_rgb)
                self.target_rgb2 = list(self.active_rgb2)
                self.pulse_anim.start()
            else:
                self.target_rgb = list(self.idle_rgb)
                self.target_rgb2 = list(self.idle_rgb2)

        self.adjustHeight(True)

    def adjustHeight(self, animate):
        doc_height = int(self.inputField.document().size().height()) + 6
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

    def triggerInvalidShake(self):
        self.error_flash = 1.0
        if self.shakeAnim is not None and self.shakeAnim.state() == QAbstractAnimation.Running:
            return

        base_y = self.y()
        bx = self.targetX
        self.shakeAnim = QPropertyAnimation(self, b"pos", self)
        self.shakeAnim.setDuration(240)
        self.shakeAnim.setKeyValueAt(0.0, QPoint(bx, base_y))
        self.shakeAnim.setKeyValueAt(0.2, QPoint(bx - 7, base_y))
        self.shakeAnim.setKeyValueAt(0.4, QPoint(bx + 7, base_y))
        self.shakeAnim.setKeyValueAt(0.6, QPoint(bx - 4, base_y))
        self.shakeAnim.setKeyValueAt(0.8, QPoint(bx + 4, base_y))
        self.shakeAnim.setKeyValueAt(1.0, QPoint(bx, base_y))
        self.shakeAnim.setEasingCurve(QEasingCurve.OutSine)
        self.shakeAnim.start()

    def triggerAccept(self):
        if self.isClosing:
            return
        raw = self.inputField.toPlainText().strip()
        if not raw and self.is_ask_mode:
            self.triggerInvalidShake()
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
        slide_down.setEndValue(QPoint(self.targetX, self.y() + 20))
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