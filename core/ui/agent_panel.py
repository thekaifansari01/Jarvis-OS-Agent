import sys
import json
import os
import re
import math
import zmq

os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false;default.warning=false"

from PyQt5.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve, 
                          QPoint, QRect, QParallelAnimationGroup, 
                          pyqtProperty, QSize, qInstallMessageHandler,
                          QThread, pyqtSignal)
from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QApplication, 
                             QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QFrame, QSizePolicy)
from PyQt5.QtGui import QFont, QColor, QFontDatabase, QFontMetrics

def qt_message_handler(mode, context, message):
    if "Unable to set geometry" in message or "Resulting geometry" in message:
        return

class AgentZmqListener(QThread):
    """Background ZMQ Subscriber Thread for zero-latency UI updates"""
    status_received = pyqtSignal(dict)
    
    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect("tcp://127.0.0.1:5555")
        
        socket.setsockopt_string(zmq.SUBSCRIBE, "AGENT_UPDATE")
        
        while True:
            try:
                message = socket.recv_string()

                topic, json_data = message.split(" ", 1)
                data = json.loads(json_data)

                self.status_received.emit(data)
            except Exception as e:
                pass


class AgentPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.last_status = None
        self.current_step = -1
        
        self.MIN_WIDTH = 380
        self.MAX_WIDTH = 750
        
        eng_id = QFontDatabase.addApplicationFont("Data/fonts/english.ttf")
        eng_fams = QFontDatabase.applicationFontFamilies(eng_id)
        self.font_eng = eng_fams[0] if eng_fams else "Segoe UI"

        hin_id = QFontDatabase.addApplicationFont("Data/fonts/devangri.ttf")
        hin_fams = QFontDatabase.applicationFontFamilies(hin_id)
        self.font_hin = hin_fams[0] if hin_fams else "Nirmala UI"

        self.gradient_phase = 0.0
        self.current_action_type = "idle"
        
        self.rgb_timer = QTimer()
        self.rgb_timer.timeout.connect(self.update_glow_effect)

        self.target_geometry = None
        self.resize_anim = QPropertyAnimation(self, b"anim_geometry")
        self.resize_anim.setEasingCurve(QEasingCurve.InOutCubic) 
        self.resize_anim.setDuration(400)

        self.initUI()
        
        self.zmq_listener = AgentZmqListener()
        self.zmq_listener.status_received.connect(self.process_status_update)
        self.zmq_listener.start()
        
        self.process_status_update({"step": 0, "thought": "", "action": "", "action_detail": "", "observation": ""})

    def minimumSizeHint(self):
        return QSize(0, 0)

    @pyqtProperty(QRect)
    def anim_geometry(self):
        return self.geometry()
        
    @anim_geometry.setter
    def anim_geometry(self, rect):
        self.setGeometry(rect)

    def initUI(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(60, 60, 60, 60)
        self.outer_layout.setSizeConstraint(QVBoxLayout.SetNoConstraint) 

        self.container = QFrame(self)
        self.container.setObjectName("IslandWrapper")
        self.container.setMinimumSize(0, 0) 
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        self.default_wrapper_style = """
            #IslandWrapper {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 28px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """
        self.container.setStyleSheet(self.default_wrapper_style)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(40) 
        self.shadow.setColor(QColor(0, 0, 0, 180)) 
        self.shadow.setOffset(0, 8) 
        self.container.setGraphicsEffect(self.shadow)

        self.wrapper_layout = QVBoxLayout(self.container)
        self.wrapper_layout.setContentsMargins(1, 1, 1, 1)
        self.wrapper_layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)

        self.inner_island = QFrame(self.container)
        self.inner_island.setObjectName("Island")
        self.inner_island.setMinimumSize(0, 0) 
        self.inner_island.setAttribute(Qt.WA_StyledBackground, True)
        self.inner_island.setStyleSheet("""
            #Island {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                                  stop:0 #151518, stop:1 #0A0A0C);
                border-radius: 27px;
            }
        """)
        self.wrapper_layout.addWidget(self.inner_island)

        self.layout = QVBoxLayout(self.inner_island)
        self.layout.setContentsMargins(28, 22, 28, 24)
        self.layout.setSpacing(14) 
        self.layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        
        self.pulse_dot = QFrame()
        self.pulse_dot.setFixedSize(10, 10)
        self.pulse_dot.setStyleSheet("background-color: #BF5AF2; border-radius: 5px;") 
        self.pulse_opacity = QGraphicsOpacityEffect(self.pulse_dot)
        self.pulse_dot.setGraphicsEffect(self.pulse_opacity)
        self.start_pulse_animation()
        
        self.status_tag = QLabel("AGENT IDLE")
        self.status_tag.setFont(QFont(self.font_eng, 9, QFont.Bold))
        self.status_tag.setStyleSheet("color: rgba(255, 255, 255, 0.8); letter-spacing: 1.2px; border: none; background: transparent;")
        
        self.status_tag.setMaximumWidth(160)
        self.status_tag.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        header_layout.addWidget(self.pulse_dot)
        header_layout.addWidget(self.status_tag)
        header_layout.addStretch()
        
        self.phase_label = QLabel("STEP: 00")
        self.phase_label.setFont(QFont(self.font_eng, 9, QFont.Bold))
        self.phase_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); letter-spacing: 1px; border: none; background: transparent;")
        
        self.phase_label.setMinimumWidth(65)
        self.phase_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.phase_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        header_layout.addWidget(self.phase_label)
        self.layout.addLayout(header_layout)
        
        self.thought_label = QLabel("")
        self.thought_label.setMinimumSize(0, 0) 
        self.thought_label.setWordWrap(True)
        self.thought_label.setAlignment(Qt.AlignCenter)
        
        thought_font = QFont(self.font_eng, 13, QFont.Medium)
        thought_font.setLetterSpacing(QFont.PercentageSpacing, 102) 
        self.thought_label.setFont(thought_font) 
        
        self.thought_label.setStyleSheet("""
            QLabel {
                color: rgba(245, 245, 250, 0.95); 
                line-height: 1.6; 
                border: none;
                background: transparent;
                padding-top: 4px;
                padding-bottom: 4px;
            }
        """)
        
        self.thought_shadow = QGraphicsDropShadowEffect(self)
        self.thought_shadow.setBlurRadius(12)
        self.thought_shadow.setColor(QColor(0, 0, 0, 160))
        self.thought_shadow.setOffset(0, 2)
        self.thought_label.setGraphicsEffect(self.thought_shadow)

        self.layout.addWidget(self.thought_label)

        self.separator = QFrame()
        self.separator.setFixedHeight(1)
        self.separator.setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0), stop:0.5 rgba(255,255,255,0.15), stop:1 rgba(255,255,255,0)); margin-top: 2px; margin-bottom: 2px;")
        self.layout.addWidget(self.separator)
        self.separator.hide() 

        self.obs_label = QLabel("")
        self.obs_label.setMinimumSize(0, 0) 
        self.obs_label.setWordWrap(True)
        self.obs_label.setAlignment(Qt.AlignCenter)
        self.obs_label.setFont(QFont(self.font_eng, 10)) 
        self.obs_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.7); 
            line-height: 1.4; 
            border: none;
            padding: 10px;
            background-color: rgba(255, 255, 255, 0.03);
            border-radius: 10px;
        """)
        self.layout.addWidget(self.obs_label)
        self.obs_label.hide() 

        self.outer_layout.addWidget(self.container)

        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_panel)
        
        self.setWindowOpacity(0.0)
        self.hide()

    def is_hindi(self, text):
        return bool(re.search(r'[\u0900-\u097F]', text))

    def set_label_font(self, label, text, base_size):
        if self.is_hindi(text):
            font = QFont(self.font_hin, base_size + 1, QFont.Medium)
            label.setFont(font)
        else:
            font = QFont(self.font_eng, base_size, QFont.Medium)
            font.setLetterSpacing(QFont.PercentageSpacing, 102)
            label.setFont(font)

    def update_glow_effect(self):
        self.gradient_phase += 0.04 
        if self.gradient_phase >= math.pi * 2:
            self.gradient_phase -= math.pi * 2 
        
        if self.current_action_type == "search":
            r, g, b = 0, 199, 255
        elif self.current_action_type == "deep_task":
            r, g, b = 255, 20, 147
        elif self.current_action_type == "thinking":
            r, g, b = 191, 90, 242
        elif self.current_action_type == "workspace":
            r, g, b = 255, 159, 10
        elif self.current_action_type == "communication":
            r, g, b = 50, 215, 75
        else:
            r, g, b = 255, 255, 255

        self.pulse_dot.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border-radius: 5px;")
        
        alpha = int(20 + math.sin(self.gradient_phase) * 15)
        alpha2 = max(0, alpha - 15)

        self.container.setStyleSheet(f"""
            #IslandWrapper {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 rgba({r}, {g}, {b}, {alpha/255.0:.3f}), 
                    stop:1 rgba({r}, {g}, {b}, {alpha2/255.0:.3f}));
                border-radius: 28px;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }}
        """)

    def reset_island_style(self):
        self.rgb_timer.stop()
        self.container.setStyleSheet(self.default_wrapper_style)
        self.shadow.setColor(QColor(0, 0, 0, 180))
        self.shadow.setBlurRadius(40)
        self.pulse_dot.setStyleSheet("background-color: #555555; border-radius: 5px;")

    def start_pulse_animation(self):
        self.p_anim = QPropertyAnimation(self.pulse_opacity, b"opacity")
        self.p_anim.setDuration(1200)
        self.p_anim.setStartValue(0.2)
        self.p_anim.setEndValue(1.0)
        self.p_anim.setLoopCount(-1)
        self.p_anim.setEasingCurve(QEasingCurve.InOutSine) 
        self.p_anim.start()

    def calculate_target_geometry(self):
        self.thought_label.setMinimumWidth(self.MIN_WIDTH - 120)
        self.thought_label.setMaximumWidth(self.MAX_WIDTH - 120)
        
        self.obs_label.setMinimumWidth(self.MIN_WIDTH - 120)
        self.obs_label.setMaximumWidth(self.MAX_WIDTH - 120)

        self.layout.activate()
        
        natural_size = self.container.sizeHint()
        
        ideal_width = max(self.MIN_WIDTH, min(natural_size.width() + 120, self.MAX_WIDTH))
        ideal_height = natural_size.height() + 120
        
        self.thought_label.setMinimumSize(0, 0)
        self.thought_label.setMaximumSize(16777215, 16777215)
        self.obs_label.setMinimumSize(0, 0)
        self.obs_label.setMaximumSize(16777215, 16777215)
        
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - ideal_width) // 2
        y = screen.top() + 25 
        
        return QRect(x, y, ideal_width, ideal_height)

    def show_panel(self):
        self.hide_timer.stop()
        
        if hasattr(self, 'hide_anim_group') and self.hide_anim_group.state() == QPropertyAnimation.Running:
            self.hide_anim_group.stop()
        if hasattr(self, 'show_anim_group') and self.show_anim_group.state() == QPropertyAnimation.Running:
            self.show_anim_group.stop()
        if self.resize_anim.state() == QPropertyAnimation.Running:
            self.resize_anim.stop()
                
        new_geometry = self.calculate_target_geometry()
            
        if not self.isVisible() or self.windowOpacity() < 1.0:
            self.target_geometry = new_geometry
            start_y = self.target_geometry.y() - 35 
            
            self.setGeometry(self.target_geometry.x(), start_y, self.target_geometry.width(), self.target_geometry.height())
            
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()

            self.show_anim_group = QParallelAnimationGroup(self)
            
            fade_in = QPropertyAnimation(self, b"windowOpacity")
            fade_in.setDuration(400)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.InOutQuad)
            
            slide_down = QPropertyAnimation(self, b"pos")
            slide_down.setDuration(500)
            slide_down.setStartValue(self.pos())
            slide_down.setEndValue(QPoint(self.target_geometry.x(), self.target_geometry.y()))
            slide_down.setEasingCurve(QEasingCurve.OutCubic) 

            self.show_anim_group.addAnimation(fade_in)
            self.show_anim_group.addAnimation(slide_down)
            self.show_anim_group.start()
            
        else:
            if self.target_geometry != new_geometry:
                self.target_geometry = new_geometry
                
                self.resize_anim.setStartValue(self.geometry())
                self.resize_anim.setEndValue(new_geometry)
                self.resize_anim.start()

    def hide_panel(self):
        if not self.isVisible(): return
        
        if hasattr(self, 'show_anim_group') and self.show_anim_group.state() == QPropertyAnimation.Running:
            self.show_anim_group.stop()
        if self.resize_anim.state() == QPropertyAnimation.Running:
            self.resize_anim.stop()

        self.hide_anim_group = QParallelAnimationGroup(self)
        
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(300)
        fade_out.setStartValue(self.windowOpacity())
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.OutQuad)
        
        slide_up = QPropertyAnimation(self, b"pos")
        slide_up.setDuration(400)
        slide_up.setStartValue(self.pos())
        slide_up.setEndValue(QPoint(self.x(), self.y() - 25))
        slide_up.setEasingCurve(QEasingCurve.OutCubic)

        self.hide_anim_group.addAnimation(fade_out)
        self.hide_anim_group.addAnimation(slide_up)
        self.hide_anim_group.finished.connect(self.hide)
        self.hide_anim_group.start()

    def process_status_update(self, status):
        if status == self.last_status:
            if self.isVisible() and status.get("step", 0) == 0:
                self.hide_timer.start(4000)
            return
        
        self.last_status = status
        step = status.get("step", 0)
        thought = status.get("thought", "")
        action = status.get("action", "")
        action_detail = status.get("action_detail", "")
        observation = status.get("observation", "")

        if step == 0:
            self.current_step = -1 
            self.reset_island_style() 
            self.hide_timer.start(2000) 
            return

        if not self.rgb_timer.isActive():
            self.rgb_timer.start(40) 

        action_map = {
            "THINKING": ("THINKING...", "thinking"),
            "search_actions": ("SEARCHING WEB", "search"),
            "deep_research": ("DEEP RESEARCH", "deep_task"),
            "workspace_action": ("WORKSPACE", "workspace"),
            "email_action": ("SENDING EMAIL", "communication"),
            "whatsapp_action": ("WHATSAPP", "communication"),
            "apps_to_open": ("OPENING APP", "workspace"),
            "urls_to_open": ("OPENING URL", "workspace"),
            "image_command": ("GENERATING IMAGE", "thinking"),
            "vision_action": ("ANALYZING SCREEN", "search"),
            "clipboard_action": ("CLIPBOARD", "workspace")
        }
        
        base_text, self.current_action_type = action_map.get(action, ("EXECUTING", "default"))
        
        full_tag_text = f"{base_text} -> {str(action_detail).upper()}" if (action_detail and action != "THINKING") else base_text
        fm = QFontMetrics(self.status_tag.font())
        elided_tag = fm.elidedText(full_tag_text, Qt.ElideRight, 155) 
        self.status_tag.setText(elided_tag)

        if self.current_step != step:
            self.phase_label.setText(f"STEP: {step:02}")
            self.current_step = step
        
        if thought:
            clean_thought = thought.strip()
            self.set_label_font(self.thought_label, clean_thought, 13)
            self.thought_label.setText(clean_thought)
        else:
            self.thought_label.setText("")

        if observation: 
            clean_obs = observation.replace("Observation:", "").strip()
            
            if len(clean_obs) > 140:
                clean_obs = clean_obs[:137] + "..."
                
            if self.obs_label.text() != clean_obs:
                self.set_label_font(self.obs_label, clean_obs, 10)
                self.obs_label.setText(f"Data: {clean_obs}")
                
                self.separator.show()
                self.obs_label.show()
        else:
            if self.obs_label.isVisible():
                self.obs_label.setText("")
                self.separator.hide()
                self.obs_label.hide()

        self.show_panel()

        if step == 0:
            self.hide_timer.start(4000)
        else:
            self.hide_timer.stop()


def run_panel():
    qInstallMessageHandler(qt_message_handler)
    
    app = QApplication(sys.argv)
    panel = AgentPanel()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_panel()