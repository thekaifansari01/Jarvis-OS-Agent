import sys
import json
import os
import random
import re
import zmq
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect, QParallelAnimationGroup, QThread, pyqtSignal
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QApplication, QGraphicsDropShadowEffect, QFrame, QSizePolicy
from PyQt5.QtGui import QFont, QColor, QFontDatabase, QPainter

class SttZmqListener(QThread):
    """Background ZMQ Subscriber Thread for STT UI updates"""
    status_received = pyqtSignal(dict)
    
    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect("tcp://127.0.0.1:5556")
        
        socket.setsockopt_string(zmq.SUBSCRIBE, "STT_UPDATE")
        
        while True:
            try:
                message = socket.recv_string()
                topic, json_data = message.split(" ", 1)
                data = json.loads(json_data)
                self.status_received.emit(data)
            except Exception as e:
                pass

class WaveformIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 18)
        self.bars = [3, 3, 3, 3] 
        self.target_bars = [3, 3, 3, 3]
        self.is_animating = False
        self.color = QColor(10, 132, 255)

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_bars)
        
    def start_animation(self, color_hex):
        self.color = QColor(color_hex)
        self.is_animating = True
        self.anim_timer.start(40)
        
    def stop_animation(self, color_hex):
        self.color = QColor(color_hex)
        self.is_animating = False
        self.target_bars = [4, 4, 4, 4] 
        
    def update_bars(self):
        if self.is_animating:
            for i in range(4):
                if abs(self.bars[i] - self.target_bars[i]) < 1:
                    self.target_bars[i] = random.randint(3, 16)
        
        needs_update = False
        for i in range(4):
            diff = self.target_bars[i] - self.bars[i]
            if abs(diff) > 0.5:
                self.bars[i] += diff * 0.35 
                needs_update = True
                
        if needs_update or self.is_animating:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)
        
        bar_width = 3
        spacing = 3
        start_x = (self.width() - (4 * bar_width + 3 * spacing)) // 2
        
        for i, height in enumerate(self.bars):
            x = start_x + i * (bar_width + spacing)
            y = (self.height() - height) / 2
            painter.drawRoundedRect(int(x), int(y), bar_width, int(height), 1, 1)


class STTPopup(QWidget):
    def __init__(self):
        super().__init__()
        
        self.font_eng = QFont("Segoe UI", 13)
        eng_id = QFontDatabase.addApplicationFont("Data/fonts/english.ttf")
        if eng_id != -1:
            fam = QFontDatabase.applicationFontFamilies(eng_id)
            if fam: self.font_eng = QFont(fam[0], 13)

        self.font_hin = QFont("Nirmala UI", 14)
        hin_id = QFontDatabase.addApplicationFont("Data/fonts/devangri.ttf")
        if hin_id != -1:
            fam = QFontDatabase.applicationFontFamilies(hin_id)
            if fam: self.font_hin = QFont(fam[0], 14)

        self.current_state = "idle"
        self.target_geometry = None
        self.resize_anim = QPropertyAnimation(self, b"geometry")
        self.resize_anim.setEasingCurve(QEasingCurve.OutExpo)
        self.resize_anim.setDuration(200)

        self.initUI()
        
        self.transcribed_timer = QTimer()
        self.transcribed_timer.setSingleShot(True)
        self.transcribed_timer.timeout.connect(self.allow_hide)
        self.can_hide = True 
        self.last_text = ""

        self.zmq_listener = SttZmqListener()
        self.zmq_listener.status_received.connect(self.process_status_update)
        self.zmq_listener.start()
        
        self.process_status_update({"status": "idle", "text": ""})

    def initUI(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(1, 1)

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(40, 40, 40, 40)

        self.island = QFrame(self)
        self.island.setObjectName("Island")
        self.island.setStyleSheet("""
            #Island {
                background-color: #000000;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 24px;
            }
        """)
        self.island.setFixedHeight(48)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(30)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setOffset(0, 4) 
        self.island.setGraphicsEffect(self.shadow)

        self.layout = QHBoxLayout(self.island)
        self.layout.setContentsMargins(22, 0, 22, 0) 
        self.layout.setSpacing(14)
        
        self.waveform = WaveformIndicator(self.island)
        self.waveform.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        self.text_label = QLabel("Listening...")
        self.text_label.setWordWrap(False)
        self.text_label.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        
        self.set_fast_text_style("Listening...", "rgba(255, 255, 255, 0.5)", QFont.Normal)
        
        self.layout.addWidget(self.waveform, 0, Qt.AlignVCenter | Qt.AlignLeft)
        self.layout.addWidget(self.text_label, 1, Qt.AlignVCenter | Qt.AlignLeft)
        
        self.outer_layout.addWidget(self.island)
        self.setWindowOpacity(0.0)
        self.hide()

    def is_hindi(self, text):
        return bool(re.search(r'[\u0900-\u097F]', text))

    def set_fast_text_style(self, text, color, weight):
        font = self.font_hin if self.is_hindi(text) else self.font_eng
        font.setWeight(weight)
        self.text_label.setFont(font)
        self.text_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self.text_label.setText(text)

    def reset_island_style(self):
        self.island.setStyleSheet("""
            #Island {
                background-color: #000000;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 24px;
            }
        """)

    def calculate_target_geometry(self):
        self.text_label.adjustSize()
        
        island_width = self.text_label.sizeHint().width() + self.waveform.width() + 60
        ideal_width = max(200, min(island_width, 800)) + 80
        ideal_height = 48 + 80
        
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - ideal_width) // 2
        y = screen.bottom() - ideal_height - 50 
        
        return QRect(int(x), int(y), int(ideal_width), int(ideal_height))

    def smooth_resize(self):
        new_geometry = self.calculate_target_geometry()
        if self.target_geometry != new_geometry:
            self.target_geometry = new_geometry
            if self.isVisible() and self.windowOpacity() > 0.8:
                if self.resize_anim.state() == QPropertyAnimation.Running:
                    self.resize_anim.stop()
                self.resize_anim.setStartValue(self.geometry())
                self.resize_anim.setEndValue(new_geometry)
                self.resize_anim.start()
            else:
                self.setGeometry(new_geometry)

    def show_panel(self):
        if hasattr(self, 'hide_anim_group') and self.hide_anim_group.state() == QPropertyAnimation.Running:
            self.hide_anim_group.stop()

        self.smooth_resize()
        
        if not self.isVisible() or self.windowOpacity() < 1.0:
            start_y = self.target_geometry.y() + 40 
            self.setGeometry(self.target_geometry.x(), start_y, self.target_geometry.width(), self.target_geometry.height())
            self.show()
            self.raise_()

            self.show_anim_group = QParallelAnimationGroup(self)
            fade_in = QPropertyAnimation(self, b"windowOpacity")
            fade_in.setDuration(200)
            fade_in.setStartValue(self.windowOpacity()) 
            fade_in.setEndValue(1.0)
            
            slide_up = QPropertyAnimation(self, b"pos")
            slide_up.setDuration(350) 
            slide_up.setStartValue(self.pos())
            slide_up.setEndValue(QPoint(self.target_geometry.x(), self.target_geometry.y()))
            slide_up.setEasingCurve(QEasingCurve.OutBack)

            self.show_anim_group.addAnimation(fade_in)
            self.show_anim_group.addAnimation(slide_up)
            self.show_anim_group.start()

    def hide_panel(self):
        if not self.isVisible(): return
        if hasattr(self, 'show_anim_group') and self.show_anim_group.state() == QPropertyAnimation.Running:
            self.show_anim_group.stop()

        self.hide_anim_group = QParallelAnimationGroup(self)
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(200)
        fade_out.setStartValue(self.windowOpacity())
        fade_out.setEndValue(0.0)
        
        slide_down = QPropertyAnimation(self, b"pos")
        slide_down.setDuration(250)
        slide_down.setStartValue(self.pos())
        slide_down.setEndValue(QPoint(self.x(), self.y() + 20))
        slide_down.setEasingCurve(QEasingCurve.InBack)

        self.hide_anim_group.addAnimation(fade_out)
        self.hide_anim_group.addAnimation(slide_down)
        self.hide_anim_group.finished.connect(self.hide)
        self.hide_anim_group.start()

    def allow_hide(self):
        self.can_hide = True
        self.process_status_update({"status": self.current_state, "text": self.last_text})

    def process_status_update(self, data):
        self.current_state = data.get("status", "idle")
        text = data.get("text", "")

        if self.current_state == "exit":
            QApplication.quit()
            return

        if self.current_state == "idle":
            self.reset_island_style() 
            self.waveform.stop_animation("#444444") 
            if not self.can_hide:
                return 
            self.hide_panel()
            self.last_text = ""
            return
            
        if self.current_state in ["listening", "understanding"]:
            self.reset_island_style()
            self.waveform.start_animation("#0A84FF")
            
            if not text.strip() and self.current_state == "listening":
                self.set_fast_text_style("Listening...", "rgba(255, 255, 255, 0.4)", QFont.Normal)
            else:
                display_text = text if text.strip() else self.last_text
                self.last_text = display_text.capitalize() if not self.is_hindi(display_text) else display_text
                self.set_fast_text_style(self.last_text, "rgba(255, 255, 255, 0.95)", QFont.Medium)
            
        elif self.current_state == "transcribed":
            self.can_hide = False
            self.transcribed_timer.start(2000) 
            self.waveform.stop_animation("#32D74B")
            
            self.island.setStyleSheet("""
                #Island {
                    background-color: #000000;
                    border: 1px solid rgba(50, 215, 75, 0.5);
                    border-radius: 24px;
                }
            """)
            
            display_text = text.capitalize() if text.strip() and not self.is_hindi(text) else (text if text.strip() else self.last_text)
            self.set_fast_text_style(display_text, "#FFFFFF", QFont.Normal)

        self.show_panel()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    panel = STTPopup()
    sys.exit(app.exec_())