import math
import re
import json
import os
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QParallelAnimationGroup, QEasingCurve
from PyQt5.QtWidgets import QWidget, QLabel, QGraphicsDropShadowEffect, QVBoxLayout, QFrame, QPushButton, QHBoxLayout, QApplication
from PyQt5.QtGui import QFont, QColor, QFontDatabase

from AsyncBrowser import AsyncTextBrowser
from TextParser import ParserWorker
from markdown2 import markdown

TYPING_STATUS_FILE = "Data/typing_status.json"

class TypingPopup(QWidget):
    def __init__(self, fallback_text="", max_width=750):
        super().__init__()
        self.max_width = max_width

        self.padding_h = 240 
        self.target_height = self.padding_h 
        self.current_height = self.padding_h
        self.max_allowed_height = 800 

        self.resize_timer = QTimer(self)
        self.resize_timer.timeout.connect(self.smooth_resize_tick)

        self.glow_phase = 0.0
        self.ambient_timer = QTimer(self)
        self.ambient_timer.timeout.connect(self.update_ambient_glow)

        self.eng_font_id = QFontDatabase.addApplicationFont("Data/fonts/english.ttf")
        self.eng_font = QFontDatabase.applicationFontFamilies(self.eng_font_id)[0] if self.eng_font_id != -1 else "Segoe UI"
        self.hin_font_id = QFontDatabase.addApplicationFont("Data/fonts/devangri.ttf")
        self.hin_font = QFontDatabase.applicationFontFamilies(self.hin_font_id)[0] if self.hin_font_id != -1 else "Nirmala UI"

        self.current_raw_text = ""
        self.status = "typing"
        self.idle_counter = 0
        
        self.init_ui()
        self.start_animations() 
        
        self.file_timer = QTimer(self)
        self.file_timer.timeout.connect(self.check_status_file)
        self.file_timer.start(50)

        self.ambient_timer.start(40) 
        self.resize_timer.start(16)  

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
        self.shadow.setBlurRadius(40); self.shadow.setOffset(0, 8); self.shadow.setColor(QColor(0, 0, 0, 180))
        self.container.setGraphicsEffect(self.shadow)

        self.wrapper_layout = QVBoxLayout(self.container)
        self.wrapper_layout.setContentsMargins(1, 1, 1, 1); self.wrapper_layout.setSpacing(0)

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
        self.container_layout.setContentsMargins(28, 22, 28, 24); self.container_layout.setSpacing(14)

        self.header_layout = QHBoxLayout()
        
        self.pulse_dot = QFrame()
        self.pulse_dot.setFixedSize(10, 10)
        self.pulse_dot.setStyleSheet("background-color: #D67CFF; border-radius: 5px;")
        
        self.status_tag = QLabel("JARVIS SPEAKING...")
        font = QFont(self.eng_font, 9, QFont.Bold); font.setLetterSpacing(QFont.PercentageSpacing, 120) 
        self.status_tag.setFont(font)
        self.status_tag.setStyleSheet("color: #D67CFF; letter-spacing: 1.5px;")
        
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(24, 24); self.close_btn.setCursor(Qt.PointingHandCursor)
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
        
        self.setWindowOpacity(0.0); self.oldPos = None

        screen = QApplication.primaryScreen().availableGeometry()
        self.max_allowed_height = int(screen.height() * 0.75)
        self.x_pos = (screen.width() - self.max_width) // 2
        self.start_y = screen.top() + 30 
        
        self.setMinimumHeight(self.padding_h); self.setFixedSize(self.max_width, self.current_height)

    def start_animations(self):
        self.setGeometry(self.x_pos, self.start_y - 20, self.max_width, self.current_height)
        self.anim_group = QParallelAnimationGroup(self)
        fade_in = QPropertyAnimation(self, b"windowOpacity")
        fade_in.setDuration(400); fade_in.setStartValue(0.0); fade_in.setEndValue(1.0)
        slide_down = QPropertyAnimation(self, b"pos")
        slide_down.setDuration(500); slide_down.setStartValue(QPoint(self.x_pos, self.start_y - 30)); slide_down.setEndValue(QPoint(self.x_pos, self.start_y))
        slide_down.setEasingCurve(QEasingCurve.OutQuart)
        
        self.anim_group.addAnimation(fade_in); self.anim_group.addAnimation(slide_down)
        self.anim_group.start(); self.show()

    def check_status_file(self):
        if not os.path.exists(TYPING_STATUS_FILE): return
            
        try:
            with open(TYPING_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            new_text = data.get("text", "")
            new_status = data.get("status", "idle")
            
            if new_text != self.current_raw_text:
                self.current_raw_text = new_text
                self.render_markdown(new_text)
                self.idle_counter = 0 
                
            self.status = new_status
            
            if self.status == "typing":
                self.status_tag.setText("JARVIS SPEAKING...")
                self.status_tag.setStyleSheet("color: #D67CFF; letter-spacing: 1.5px;")
                self.separator.setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0), stop:0.5 rgba(191, 90, 242, 0.4), stop:1 rgba(255,255,255,0));")
            elif self.status == "completed":
                self.status_tag.setText("READING MODE (Click ✕ to close)")
                self.status_tag.setStyleSheet("color: #32D74B; letter-spacing: 1.5px;")
                self.separator.setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0), stop:0.5 rgba(50, 215, 75, 0.4), stop:1 rgba(255,255,255,0));")
                
                self.idle_counter += 1
                
                word_count = len(self.current_raw_text.split())
                
                if word_count < 40:
                    if self.idle_counter > 80:
                        self.fade_out()
                else:
                    pass
                    
        except Exception:
            pass 

    def render_markdown(self, raw_text):
        scrollbar = self.text_browser.verticalScrollBar()
        is_at_bottom = scrollbar.value() >= scrollbar.maximum() - 15

        worker = ParserWorker(raw_text, self.eng_font, self.hin_font)
        text = worker.process_markdown_code_blocks(raw_text)
        text = worker.process_md_images(text)
        text = worker.process_md_links(text)
        text = worker.process_raw_direct_images(text)
        text = worker.process_youtube_links(text)
        text = worker.process_raw_links(text)
        
        md_html = markdown(text, extras=["tables", "cuddled-lists", "strike", "break-on-newline", "html-classes", "fenced-code-blocks"])
        md_html = re.sub(r'<p>\s*(<jarvis-token-\d+/>)\s*</p>', r'\1', md_html)
        
        for token, value in worker.protected_elements.items():
            md_html = md_html.replace(token, value)
            
        final_html = worker.get_styled_html(md_html)
        self.text_browser.setHtml(final_html)
        
        self.update_layout_height()
        
        if is_at_bottom or self.status == "typing":
            scrollbar.setValue(scrollbar.maximum())

    def smooth_resize_tick(self):
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
            self.current_height += (self.target_height - self.current_height) * 0.15
            self.setFixedHeight(int(self.current_height))
        elif self.current_height != self.target_height:
            self.current_height = self.target_height
            self.setFixedHeight(int(self.current_height))

        if getattr(self, 'auto_scroll_enabled', True) and self.current_height >= self.max_allowed_height - 10:
            if cur_v < max_v:
                new_v = cur_v + (max_v - cur_v) * 0.15 
                if (max_v - cur_v) <= 2: 
                    new_v = max_v
                scrollbar.setValue(int(new_v))
                self.last_scroll_value = int(new_v)
            else:
                self.last_scroll_value = cur_v
        else:
            self.last_scroll_value = cur_v

    def update_layout_height(self):
        self.target_height = min(self.text_browser.document().size().height() + self.padding_h, self.max_allowed_height)

    def update_ambient_glow(self):
        self.glow_phase += 0.05
        if self.glow_phase > math.pi * 2: self.glow_phase -= math.pi * 2
        
        if self.status == "typing":
            alpha = int(100 + 40 * math.sin(self.glow_phase * 1.5))
            self.shadow.setColor(QColor(191, 90, 242, alpha))
            self.pulse_dot.setStyleSheet(f"background-color: rgba(214, 124, 255, {alpha/255.0}); border-radius: 5px;")
        else:
            self.shadow.setColor(QColor(50, 215, 75, 80))
            self.pulse_dot.setStyleSheet("background-color: #32D74B; border-radius: 5px;")

    def fade_out(self):
        if not self.isVisible(): return
        self.ambient_timer.stop()
        self.resize_timer.stop()
        self.file_timer.stop()
            
        self.out_anim_group = QParallelAnimationGroup(self)
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(300); fade_out.setStartValue(self.windowOpacity()); fade_out.setEndValue(0.0)
        slide_up = QPropertyAnimation(self, b"pos")
        slide_up.setDuration(400); slide_up.setStartValue(self.pos()); slide_up.setEndValue(QPoint(self.x(), self.y() - 25))
        self.out_anim_group.addAnimation(fade_out); self.out_anim_group.addAnimation(slide_up)
        
        self.out_anim_group.finished.connect(lambda: QApplication.quit())
        self.out_anim_group.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self.oldPos = event.globalPos()
    def mouseMoveEvent(self, event):
        if self.oldPos is not None:
            delta = QPoint(event.globalPos() - self.oldPos); self.move(self.x() + delta.x(), self.y() + delta.y()); self.oldPos = event.globalPos()
    def mouseReleaseEvent(self, event): self.oldPos = None