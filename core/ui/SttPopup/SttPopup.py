import sys
import os
import random
import json
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QHBoxLayout, 
                             QVBoxLayout, QFrame, QGraphicsDropShadowEffect, QSizePolicy)
from PyQt5.QtCore import (Qt, QTimer, QPropertyAnimation, QParallelAnimationGroup, 
                          QSequentialAnimationGroup, QEasingCurve, QPoint, QRect, QRectF, pyqtProperty)
from PyQt5.QtGui import (QColor, QPainter, QFont, QFontDatabase)
from PyQt5.QtNetwork import QUdpSocket, QHostAddress

class WaveformIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 18)
        self.bars = [3.0, 3.0, 3.0, 3.0]
        self.target_bars = [3.0, 3.0, 3.0, 3.0]
        self.is_animating = False
        self.color = QColor("#0A84FF")
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_bars)

    def start_animation(self, color_hex):
        self.color = QColor(color_hex)
        self.is_animating = True
        self.anim_timer.start(8)

    def stop_animation(self, color_hex):
        self.color = QColor(color_hex)
        self.is_animating = False
        self.target_bars = [4.0, 4.0, 4.0, 4.0]

    def update_bars(self):
        if self.is_animating:
            for i in range(4):
                if abs(self.bars[i] - self.target_bars[i]) < 0.5:
                    self.target_bars[i] = random.uniform(3.0, 16.0)
        needs_update = False
        for i in range(4):
            diff = self.target_bars[i] - self.bars[i]
            if abs(diff) > 0.05:
                self.bars[i] += diff * 0.12
                needs_update = True
        if needs_update or self.is_animating:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)
        bar_width = 3.5
        spacing = 3.0
        start_x = (self.width() - (4 * bar_width + 3 * spacing)) / 2.0
        for i in range(4):
            x = start_x + i * (bar_width + spacing)
            height = max(3.0, self.bars[i])
            y = (self.height() - height) / 2.0
            painter.drawRoundedRect(QRectF(x, y, bar_width, height), bar_width / 2.0, bar_width / 2.0)


class IslandFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._borderColor = QColor(255, 255, 255, 25)
        self._bgColor = QColor(12, 12, 12, 255)
        self.update_style()

    @pyqtProperty(QColor)
    def borderColor(self):
        return self._borderColor

    @borderColor.setter
    def borderColor(self, color):
        self._borderColor = color
        self.update_style()

    @pyqtProperty(QColor)
    def bgColor(self):
        return self._bgColor

    @bgColor.setter
    def bgColor(self, color):
        self._bgColor = color
        self.update_style()

    def update_style(self):
        r, g, b, a = self._borderColor.red(), self._borderColor.green(), self._borderColor.blue(), self._borderColor.alpha()
        br, bg, bb, ba = self._bgColor.red(), self._bgColor.green(), self._bgColor.blue(), self._bgColor.alpha()
        self.setStyleSheet(f"background-color: rgba({br}, {bg}, {bb}, {ba/255.0}); border: 1.5px solid rgba({r}, {g}, {b}, {a/255.0}); border-radius: 24px;")


class STTPopup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "idle"
        self.can_hide = True
        self.last_text = ""
        self.transcribed_anim_group = None
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        eng_font_path = os.path.join(base_dir, "Data", "fonts", "english.ttf")
        hin_font_path = os.path.join(base_dir, "Data", "fonts", "devangri.ttf")

        self.font_eng = QFont("Segoe UI", 13)
        eng_id = QFontDatabase.addApplicationFont(eng_font_path)
        if eng_id != -1:
            fams = QFontDatabase.applicationFontFamilies(eng_id)
            if fams:
                self.font_eng = QFont(fams[0], 13)

        self.font_hin = QFont("Nirmala UI", 14)
        hin_id = QFontDatabase.addApplicationFont(hin_font_path)
        if hin_id != -1:
            fams = QFontDatabase.applicationFontFamilies(hin_id)
            if fams:
                self.font_hin = QFont(fams[0], 14)

        self.resize_anim = QPropertyAnimation(self, b"geometry", self)
        self.resize_anim.setEasingCurve(QEasingCurve.OutQuart)
        self.resize_anim.setDuration(400)

        self.show_anim_group = QParallelAnimationGroup(self)
        self.hide_anim_group = QParallelAnimationGroup(self)

        self.transcribed_timer = QTimer(self)
        self.transcribed_timer.setSingleShot(True)
        self.transcribed_timer.timeout.connect(self.allow_hide)

        self.target_geometry = QRect()

        self.initUI()
        self.setup_pulse_animation()

        self.udpSocket = QUdpSocket(self)
        self.udpSocket.bind(QHostAddress.LocalHost, 5556)
        self.udpSocket.readyRead.connect(self.readPendingDatagrams)
        self.process_status_update({"status": "idle", "text": ""})

    def setup_pulse_animation(self):
        self.pulse_anim = QSequentialAnimationGroup(self)
        
        in_group = QParallelAnimationGroup(self)
        b_in = QPropertyAnimation(self.island, b"borderColor")
        b_in.setDuration(1200)
        b_in.setStartValue(QColor(10, 132, 255, 30))
        b_in.setEndValue(QColor(10, 132, 255, 180))
        b_in.setEasingCurve(QEasingCurve.InOutSine)
        bg_in = QPropertyAnimation(self.island, b"bgColor")
        bg_in.setDuration(1200)
        bg_in.setStartValue(QColor(12, 12, 12, 255))
        bg_in.setEndValue(QColor(15, 28, 45, 255))
        bg_in.setEasingCurve(QEasingCurve.InOutSine)
        in_group.addAnimation(b_in)
        in_group.addAnimation(bg_in)

        out_group = QParallelAnimationGroup(self)
        b_out = QPropertyAnimation(self.island, b"borderColor")
        b_out.setDuration(1200)
        b_out.setStartValue(QColor(10, 132, 255, 180))
        b_out.setEndValue(QColor(10, 132, 255, 30))
        b_out.setEasingCurve(QEasingCurve.InOutSine)
        bg_out = QPropertyAnimation(self.island, b"bgColor")
        bg_out.setDuration(1200)
        bg_out.setStartValue(QColor(15, 28, 45, 255))
        bg_out.setEndValue(QColor(12, 12, 12, 255))
        bg_out.setEasingCurve(QEasingCurve.InOutSine)
        out_group.addAnimation(b_out)
        out_group.addAnimation(bg_out)

        self.pulse_anim.addAnimation(in_group)
        self.pulse_anim.addAnimation(out_group)
        self.pulse_anim.setLoopCount(-1)

    def readPendingDatagrams(self):
        while self.udpSocket.hasPendingDatagrams():
            datagram, host, port = self.udpSocket.readDatagram(self.udpSocket.pendingDatagramSize())
            try:
                data = json.loads(datagram.decode('utf-8'))
                if isinstance(data, dict):
                    self.process_status_update(data)
            except Exception:
                pass

    def initUI(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(1, 1)

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(40, 40, 40, 40)

        self.island = IslandFrame(self)
        self.island.setObjectName("Island")
        self.island.setFixedHeight(48)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(40)
        self.shadow.setColor(QColor(0, 0, 0, 120))
        self.shadow.setOffset(0, 8)
        self.island.setGraphicsEffect(self.shadow)

        self.layout = QHBoxLayout(self.island)
        self.layout.setContentsMargins(22, 0, 24, 0)
        self.layout.setSpacing(16)

        self.waveform = WaveformIndicator(self.island)
        self.waveform.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.text_label = QLabel("Listening...", self.island)
        self.text_label.setWordWrap(False)
        self.text_label.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.set_fast_text_style("Listening...", "rgba(255, 255, 255, 0.4)", QFont.Normal)

        self.layout.addWidget(self.waveform, 0, Qt.AlignVCenter | Qt.AlignLeft)
        self.layout.addWidget(self.text_label, 1, Qt.AlignVCenter | Qt.AlignLeft)

        self.outer_layout.addWidget(self.island)
        self.setWindowOpacity(0.0)
        self.hide()

    def format_text(self, text):
        words = text.strip().split()
        if len(words) > 8:
            return "... " + " ".join(words[-8:])
        return text.strip()

    def is_hindi(self, text):
        for char in text:
            if '\u0900' <= char <= '\u097F':
                return True
        return False

    def set_fast_text_style(self, text, color, weight):
        font = self.font_hin if self.is_hindi(text) else self.font_eng
        font.setWeight(weight)
        self.text_label.setFont(font)
        self.text_label.setStyleSheet(f"color: {color}; background: transparent; border: none; letter-spacing: 0.3px;")
        self.text_label.setText(text)

    def calculate_target_geometry(self):
        self.text_label.adjustSize()
        island_width = self.text_label.sizeHint().width() + self.waveform.width() + 66
        ideal_width = max(210, min(island_width, 800)) + 80
        ideal_height = 48 + 80
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - ideal_width) // 2
        y = screen.bottom() - ideal_height - 60
        return QRect(x, y, ideal_width, ideal_height)

    def smooth_resize(self):
        new_geometry = self.calculate_target_geometry()
        if self.target_geometry != new_geometry:
            self.target_geometry = new_geometry
            if self.isVisible() and self.windowOpacity() > 0.5:
                if self.resize_anim.state() == QPropertyAnimation.Running:
                    self.resize_anim.stop()
                self.resize_anim.setStartValue(self.geometry())
                self.resize_anim.setEndValue(new_geometry)
                self.resize_anim.start()
            else:
                self.setGeometry(new_geometry)

    def show_panel(self):
        if self.hide_anim_group.state() == QPropertyAnimation.Running:
            self.hide_anim_group.stop()
        self.smooth_resize()
        if not self.isVisible() or self.windowOpacity() < 1.0:
            start_y = self.target_geometry.y() + 35
            self.setGeometry(self.target_geometry.x(), start_y, self.target_geometry.width(), self.target_geometry.height())
            self.show()
            self.raise_()
            self.show_anim_group.clear()
            fade_in = QPropertyAnimation(self, b"windowOpacity")
            fade_in.setDuration(300)
            fade_in.setStartValue(self.windowOpacity())
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.OutCubic)
            slide_up = QPropertyAnimation(self, b"pos")
            slide_up.setDuration(450)
            slide_up.setStartValue(self.pos())
            slide_up.setEndValue(QPoint(self.target_geometry.x(), self.target_geometry.y()))
            slide_up.setEasingCurve(QEasingCurve.OutQuart)
            self.show_anim_group.addAnimation(fade_in)
            self.show_anim_group.addAnimation(slide_up)
            self.show_anim_group.start()

    def hide_panel(self):
        if not self.isVisible():
            return
        if self.show_anim_group.state() == QPropertyAnimation.Running:
            self.show_anim_group.stop()
        self.hide_anim_group.clear()
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(250)
        fade_out.setStartValue(self.windowOpacity())
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)
        slide_down = QPropertyAnimation(self, b"pos")
        slide_down.setDuration(350)
        slide_down.setStartValue(self.pos())
        slide_down.setEndValue(QPoint(self.x(), self.y() + 25))
        slide_down.setEasingCurve(QEasingCurve.InQuart)
        self.hide_anim_group.addAnimation(fade_out)
        self.hide_anim_group.addAnimation(slide_down)
        try:
            self.hide_anim_group.finished.disconnect(self.hide_panel_finished)
        except TypeError:
            pass
        self.hide_anim_group.finished.connect(self.hide_panel_finished)
        self.hide_anim_group.start()

    def hide_panel_finished(self):
        self.hide()

    def allow_hide(self):
        self.can_hide = True
        self.process_status_update({"status": self.current_state, "text": self.last_text})

    def process_status_update(self, data):
        self.current_state = data.get("status", "idle")
        raw_text = data.get("text", "")

        if self.current_state == "exit":
            QApplication.quit()
            return

        if self.current_state == "idle":
            self.pulse_anim.stop()
            self.island.borderColor = QColor(255, 255, 255, 25)
            self.island.bgColor = QColor(12, 12, 12, 255)
            self.waveform.stop_animation("#555555")
            if not self.can_hide:
                return
            self.hide_panel()
            self.last_text = ""
            return

        if self.current_state in ["listening", "understanding"]:
            if self.pulse_anim.state() != QPropertyAnimation.Running:
                self.pulse_anim.start()
            self.waveform.start_animation("#0A84FF")
            
            if not raw_text.strip() and self.current_state == "listening":
                self.set_fast_text_style("Listening...", "rgba(255, 255, 255, 0.4)", QFont.Normal)
            else:
                display_text = self.format_text(raw_text) or self.format_text(self.last_text)
                if not self.is_hindi(display_text) and display_text and not display_text.startswith("..."):
                    display_text = display_text[0].upper() + display_text[1:]
                self.last_text = raw_text
                self.set_fast_text_style(display_text, "rgba(255, 255, 255, 0.98)", QFont.Medium)
                
        elif self.current_state == "transcribed":
            self.can_hide = False
            self.transcribed_timer.start(2500)
            self.pulse_anim.stop()
            self.waveform.stop_animation("#32D74B")
            
            self.transcribed_anim_group = QParallelAnimationGroup(self)
            b_anim = QPropertyAnimation(self.island, b"borderColor")
            b_anim.setDuration(800)
            b_anim.setStartValue(QColor(50, 215, 75, 200))
            b_anim.setEndValue(QColor(255, 255, 255, 25))
            b_anim.setEasingCurve(QEasingCurve.OutCubic)
            
            bg_anim = QPropertyAnimation(self.island, b"bgColor")
            bg_anim.setDuration(800)
            bg_anim.setStartValue(QColor(15, 45, 25, 255))
            bg_anim.setEndValue(QColor(12, 12, 12, 255))
            bg_anim.setEasingCurve(QEasingCurve.OutCubic)
            
            self.transcribed_anim_group.addAnimation(b_anim)
            self.transcribed_anim_group.addAnimation(bg_anim)
            self.transcribed_anim_group.start()
            
            display_text = self.format_text(raw_text) or self.format_text(self.last_text)
            if display_text and not self.is_hindi(display_text) and not display_text.startswith("..."):
                display_text = display_text[0].upper() + display_text[1:]
            self.set_fast_text_style(display_text, "#FFFFFF", QFont.Normal)
            
        self.show_panel()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    panel = STTPopup()
    sys.exit(app.exec_())