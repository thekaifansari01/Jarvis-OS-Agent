import math
import os
import json
import time
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QParallelAnimationGroup, QEasingCurve, QFileSystemWatcher
from PyQt5.QtWidgets import QWidget, QLabel, QGraphicsDropShadowEffect, QVBoxLayout, QFrame, QPushButton, QHBoxLayout, QApplication
from PyQt5.QtGui import QFont, QColor, QFontDatabase

from AsyncBrowser import AsyncTextBrowser
from TextParser import ParserWorker

TYPING_STATUS_FILE = "Data/typing_status.json"

class TypingPopup(QWidget):
    def __init__(self, fallback_text="", max_width=750):
        super().__init__()
        self.max_width = max_width
        self.padding_h = 240
        self.target_height = self.padding_h
        self.current_height = self.padding_h
        self.max_allowed_height = 850

        self.glow_phase = 0.0
        self.last_pulse_alpha = -1
        self._last_mtime = 0

        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.master_tick)

        self.parse_debounce_timer = QTimer(self)
        self.parse_debounce_timer.setSingleShot(True)
        self.parse_debounce_timer.timeout.connect(self._execute_parse)

        self.eng_font_id = QFontDatabase.addApplicationFont("Data/fonts/english.ttf")
        self.eng_font = QFontDatabase.applicationFontFamilies(self.eng_font_id)[0] if self.eng_font_id != -1 else "Segoe UI"
        self.hin_font_id = QFontDatabase.addApplicationFont("Data/fonts/devangri.ttf")
        self.hin_font = QFontDatabase.applicationFontFamilies(self.hin_font_id)[0] if self.hin_font_id != -1 else "Nirmala UI"

        self.current_raw_text = ""
        self.pending_raw_text = ""
        self.status = "typing"
        self.idle_counter = 0
        self.worker = None
        self.is_fading_out = False

        self.init_ui()
        self.start_animations()

        self.file_watcher = QFileSystemWatcher(self)
        if os.path.exists(TYPING_STATUS_FILE):
            self.file_watcher.addPath(TYPING_STATUS_FILE)
        self.file_watcher.fileChanged.connect(self.on_status_file_changed)

        self.master_timer.start(16)
        self.check_status_file()

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(60, 60, 60, 60)

        self.container = QFrame(self)
        self.container.setObjectName("IslandWrapper")
        self.container.setStyleSheet("""
            #IslandWrapper { 
                background-color: rgba(20, 20, 25, 0.6); 
                border-radius: 28px; 
                border: 1px solid rgba(255, 255, 255, 0.08); 
            }
        """)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(40)
        self.shadow.setOffset(0, 8)
        self.shadow.setColor(QColor(191, 90, 242, 100))
        self.container.setGraphicsEffect(self.shadow)

        self.wrapper_layout = QVBoxLayout(self.container)
        self.wrapper_layout.setContentsMargins(1, 1, 1, 1)
        self.wrapper_layout.setSpacing(0)

        self.inner_island = QFrame(self.container)
        self.inner_island.setObjectName("Island")
        self.inner_island.setStyleSheet("""
            #Island { 
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121216, stop:1 #08080A); 
                border-radius: 27px; 
            }
        """)
        self.wrapper_layout.addWidget(self.inner_island)

        self.container_layout = QVBoxLayout(self.inner_island)
        self.container_layout.setContentsMargins(28, 22, 28, 24)
        self.container_layout.setSpacing(14)

        self.header_layout = QHBoxLayout()
        
        self.pulse_dot = QFrame()
        self.pulse_dot.setFixedSize(10, 10)
        self.pulse_dot.setStyleSheet("background-color: #D67CFF; border-radius: 5px;")
        
        self.status_tag = QLabel("JARVIS SPEAKING...")
        font = QFont(self.eng_font, 9, QFont.Bold)
        font.setLetterSpacing(QFont.PercentageSpacing, 120)
        self.status_tag.setFont(font)
        self.status_tag.setStyleSheet("color: #D67CFF; letter-spacing: 1.5px;")
        
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton { 
                color: rgba(255,255,255,0.4); 
                background: rgba(255,255,255,0.05); 
                border: 1px solid rgba(255,255,255,0.05);
                font-weight: bold; 
                border-radius: 12px; 
            } 
            QPushButton:hover { 
                color: #ffffff; 
                background: rgba(255, 59, 48, 0.9); 
                border: none;
            }
        """)
        self.close_btn.clicked.connect(self.fade_out)

        self.header_layout.addWidget(self.pulse_dot)
        self.header_layout.addWidget(self.status_tag)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.close_btn)
        self.container_layout.addLayout(self.header_layout)

        self.separator = QFrame()
        self.separator.setFixedHeight(1)
        self.separator.setStyleSheet("""
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
            stop:0 rgba(255,255,255,0), 
            stop:0.5 rgba(191, 90, 242, 0.4), 
            stop:1 rgba(255,255,255,0));
        """)
        self.container_layout.addWidget(self.separator)

        self.text_browser = AsyncTextBrowser(self)
        self.container_layout.addWidget(self.text_browser)
        self.outer_layout.addWidget(self.container)
        
        self.setWindowOpacity(0.0)
        self.oldPos = None

        screen = QApplication.primaryScreen().availableGeometry()
        self.max_allowed_height = int(screen.height() * 0.78)
        self.x_pos = (screen.width() - self.max_width) // 2
        self.start_y = screen.top() + 30
        
        self.setMinimumHeight(self.padding_h)
        self.setFixedSize(self.max_width, self.current_height)

    def start_animations(self):
        self.is_fading_out = False
        self.setGeometry(self.x_pos, self.start_y - 20, self.max_width, self.current_height)
        self.anim_group = QParallelAnimationGroup(self)
        fade_in = QPropertyAnimation(self, b"windowOpacity")
        fade_in.setDuration(350)
        fade_in.setStartValue(self.windowOpacity())
        fade_in.setEndValue(1.0)
        slide_down = QPropertyAnimation(self, b"pos")
        slide_down.setDuration(400)
        slide_down.setStartValue(QPoint(self.x_pos, self.start_y - 20))
        slide_down.setEndValue(QPoint(self.x_pos, self.start_y))
        slide_down.setEasingCurve(QEasingCurve.OutQuart)
        
        self.anim_group.addAnimation(fade_in)
        self.anim_group.addAnimation(slide_down)
        self.anim_group.start()
        self.show()

    def on_status_file_changed(self, path):
        QTimer.singleShot(10, self.check_status_file)
        if os.path.exists(TYPING_STATUS_FILE) and TYPING_STATUS_FILE not in self.file_watcher.files():
            self.file_watcher.addPath(TYPING_STATUS_FILE)

    def check_status_file(self):
        if not os.path.exists(TYPING_STATUS_FILE):
            return
            
        data = None
        for _ in range(3):
            try:
                with open(TYPING_STATUS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                break
            except Exception:
                time.sleep(0.005)
                
        if not data:
            return

        new_text = data.get("text", "")
        new_status = data.get("status", "idle")
        
        if new_status in ("typing", "completed"):
            self.idle_counter = 0
            if not self.isVisible() or self.is_fading_out or self.windowOpacity() < 0.1:
                self.start_animations()
                
        if new_text != self.current_raw_text:
            self.current_raw_text = new_text
            self.render_markdown_async(new_text)
            
        if new_status != self.status:
            self.status = new_status
            if self.status == "typing":
                self.status_tag.setText("JARVIS SPEAKING...")
                self.status_tag.setStyleSheet("color: #D67CFF; letter-spacing: 1.5px;")
                self.separator.setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0), stop:0.5 rgba(191, 90, 242, 0.4), stop:1 rgba(255,255,255,0));")
            elif self.status == "completed":
                self.status_tag.setText("READING MODE (Click ✕ to close)")
                self.status_tag.setStyleSheet("color: #32D74B; letter-spacing: 1.5px;")
                self.separator.setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0), stop:0.5 rgba(50, 215, 75, 0.4), stop:1 rgba(255,255,255,0));")
                self.pulse_dot.setStyleSheet("background-color: #32D74B; border-radius: 5px;")
                self.shadow.setColor(QColor(50, 215, 75, 80))
        
        if self.status == "completed":
            self.idle_counter += 1
            word_count = len(self.current_raw_text.split())
            if word_count < 40 and self.idle_counter > 80:
                self.fade_out()

    def render_markdown_async(self, raw_text):
        self.pending_raw_text = raw_text
        self.parse_debounce_timer.start(50)

    def _execute_parse(self):
        if not self.pending_raw_text:
            return
        if self.worker is not None and self.worker.isRunning():
            self.worker.is_cancelled = True
            self.parse_debounce_timer.start(20)
            return

        self.worker = ParserWorker(self.pending_raw_text, self.eng_font, self.hin_font)
        self.worker.finished_signal.connect(self.on_markdown_parsed)
        self.worker.start()

    def on_markdown_parsed(self, tokens, final_html):
        scrollbar = self.text_browser.verticalScrollBar()
        was_at_bottom = (scrollbar.value() >= scrollbar.maximum() - 15) or self.status == "typing"
        
        self.text_browser.setHtml(final_html)
        self.update_layout_height()
        
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
            self.last_scroll_value = scrollbar.maximum()

    def master_tick(self):
        try:
            if os.path.exists(TYPING_STATUS_FILE):
                mtime = os.path.getmtime(TYPING_STATUS_FILE)
                if mtime != self._last_mtime:
                    self._last_mtime = mtime
                    self.check_status_file()
        except Exception:
            pass

        scrollbar = self.text_browser.verticalScrollBar()
        cur_v = scrollbar.value()
        max_v = scrollbar.maximum()

        if hasattr(self, 'last_scroll_value'):
            if cur_v < self.last_scroll_value - 5:
                self.auto_scroll_enabled = False
            elif cur_v >= max_v - 15:
                self.auto_scroll_enabled = True
        else:
            self.auto_scroll_enabled = True

        if abs(self.target_height - self.current_height) > 1:
            self.current_height += (self.target_height - self.current_height) * 0.22
            self.setFixedHeight(int(self.current_height))
        elif self.current_height != self.target_height:
            self.current_height = self.target_height
            self.setFixedHeight(int(self.current_height))

        if getattr(self, 'auto_scroll_enabled', True) and self.current_height >= self.max_allowed_height - 10:
            if cur_v < max_v:
                new_v = cur_v + (max_v - cur_v) * 0.25
                if (max_v - cur_v) <= 2:
                    new_v = max_v
                scrollbar.setValue(int(new_v))
                self.last_scroll_value = int(new_v)
            else:
                self.last_scroll_value = cur_v
        else:
            self.last_scroll_value = cur_v

        if self.status == "typing":
            self.glow_phase += 0.03
            if self.glow_phase > math.pi * 2:
                self.glow_phase -= math.pi * 2
            alpha = int(100 + 40 * math.sin(self.glow_phase * 1.5))
            self.shadow.setColor(QColor(191, 90, 242, alpha))
            if abs(alpha - self.last_pulse_alpha) >= 6:
                self.pulse_dot.setStyleSheet(f"background-color: rgba(214, 124, 255, {alpha/255.0:.2f}); border-radius: 5px;")
                self.last_pulse_alpha = alpha

    def update_layout_height(self):
        doc = self.text_browser.document()
        doc.setTextWidth(max(10, self.text_browser.viewport().width()))
        doc_height = int(doc.size().height())
        new_target = min(doc_height + self.padding_h, self.max_allowed_height)
        if abs(new_target - self.target_height) > 4:
            self.target_height = max(self.padding_h, new_target)

    def fade_out(self):
        if not self.isVisible() or self.is_fading_out:
            return
        self.is_fading_out = True
        self.master_timer.stop()
        self.parse_debounce_timer.stop()
            
        self.out_anim_group = QParallelAnimationGroup(self)
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(300)
        fade_out.setStartValue(self.windowOpacity())
        fade_out.setEndValue(0.0)
        slide_up = QPropertyAnimation(self, b"pos")
        slide_up.setDuration(400)
        slide_up.setStartValue(self.pos())
        slide_up.setEndValue(QPoint(self.x(), self.y() - 25))
        self.out_anim_group.addAnimation(fade_out)
        self.out_anim_group.addAnimation(slide_up)
        
        self.out_anim_group.finished.connect(lambda: QApplication.quit())
        self.out_anim_group.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.oldPos is not None:
            delta = QPoint(event.globalPos() - self.oldPos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.oldPos = None