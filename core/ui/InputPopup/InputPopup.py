import sys
import os
from PyQt5.QtWidgets import (QApplication, QDialog, QFrame, QTextEdit, QLabel, 
                             QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect, QSizePolicy)
from PyQt5.QtCore import (Qt, QPropertyAnimation, QParallelAnimationGroup, 
                          QEasingCurve, QPoint, QRect, QRectF, pyqtProperty, QTimer, QAbstractAnimation)
from PyQt5.QtGui import (QColor, QPainter, QLinearGradient, QPainterPath, 
                         QPen, QFontDatabase, QFont, QPixmap)

class GlassContainer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bgColor = QColor(14, 14, 18, int(255 * 0.78))
        self._borderColor = QColor(255, 255, 255, int(255 * 0.15))

    @pyqtProperty(QColor)
    def bgColor(self):
        return self._bgColor

    @bgColor.setter
    def bgColor(self, color):
        self._bgColor = color
        self.update()

    @pyqtProperty(QColor)
    def borderColor(self):
        return self._borderColor

    @borderColor.setter
    def borderColor(self, color):
        self._borderColor = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bgGradient = QLinearGradient(0, 0, self.width(), self.height())
        r, g, b, a = self._bgColor.red(), self._bgColor.green(), self._bgColor.blue(), self._bgColor.alpha()

        bgGradient.setColorAt(0.0, QColor(min(255, r + 20), min(255, g + 20), min(255, b + 25), a))
        bgGradient.setColorAt(0.5, self._bgColor)
        bgGradient.setColorAt(1.0, QColor(max(0, r - 8), max(0, g - 8), max(0, b - 10), min(255, a + 15)))

        rect = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 24.0, 24.0)

        painter.fillPath(path, bgGradient)

        innerHighlight = QPainterPath()
        innerHighlight.addRoundedRect(QRectF(rect.adjusted(1, 1, -1, -1)), 23.0, 23.0)
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1.0))
        painter.drawPath(innerHighlight)

        painter.setPen(QPen(self._borderColor, 1.5))
        painter.drawPath(path)

class SmartInput(QTextEdit):
    def __init__(self, parentPopup, parent=None):
        super().__init__(parent)
        self.m_parentPopup = parentPopup
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptRichText(False)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.m_parentPopup.triggerAccept()
        elif event.key() == Qt.Key_Escape:
            self.m_parentPopup.triggerReject()
        else:
            super().keyPressEvent(event)

class InputPopup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.isClosing = False
        self.isTypingMode = False
        self.commandText = ""
        self.resizeAnimGroup = None
        self.outAnimGroup = None

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        font_path = os.path.join(base_dir, "Data", "fonts", "english.ttf")
        
        fontId = QFontDatabase.addApplicationFont(font_path)
        if fontId != -1:
            self.customFontFamily = QFontDatabase.applicationFontFamilies(fontId)[0]
        else:
            self.customFontFamily = "Segoe UI"

        self.initUI(base_dir)
        QTimer.singleShot(50, self.forceFocus)

    def initUI(self, base_dir):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(700)

        outerLayout = QVBoxLayout(self)
        outerLayout.setContentsMargins(25, 25, 25, 30)

        self.container = GlassContainer(self)
        
        containerLayout = QHBoxLayout(self.container)
        containerLayout.setContentsMargins(26, 18, 24, 18)
        containerLayout.setSpacing(18)
        containerLayout.setAlignment(Qt.AlignTop)

        self.iconLabel = QLabel(self.container)
        icon_path = os.path.join(base_dir, "Data", "icons", "jarvis_icon.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.iconLabel.setPixmap(pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.iconLabel.setText("⚡")
            self.iconLabel.setFont(QFont("Segoe UI Emoji", 16))
            self.iconLabel.setStyleSheet("color: rgba(255,255,255,0.75);")
        self.iconLabel.setStyleSheet("background: transparent; margin-top: 0px;")
        containerLayout.addWidget(self.iconLabel, 0, Qt.AlignTop)

        self.inputField = SmartInput(self, self.container)
        self.inputField.setPlaceholderText("What do you need?")
        self.inputField.setStyleSheet(f"""
            QTextEdit {{ background: transparent; color: rgba(255, 255, 255, 0.98); border: none; 
            font-family: "{self.customFontFamily}"; font-size: 17px; letter-spacing: 0.4px; 
            selection-background-color: rgba(0, 240, 255, 0.35); selection-color: #FFFFFF; line-height: 1.6; }}
            QTextEdit::placeholder {{ color: rgba(255, 255, 255, 0.22); font-weight: 300; }}
        """)
        containerLayout.addWidget(self.inputField)

        self.enterIndicator = QLabel("↵", self.container)
        self.enterIndicator.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.enterIndicator.setStyleSheet("color: #00F0FF; background: transparent;")
        self.enterIndicator.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.indicatorOpacity = QGraphicsOpacityEffect(self.enterIndicator)
        self.indicatorOpacity.setOpacity(0.04)
        self.enterIndicator.setGraphicsEffect(self.indicatorOpacity)
        containerLayout.addWidget(self.enterIndicator, 0, Qt.AlignTop)

        outerLayout.addWidget(self.container)

        self.inputField.textChanged.connect(self.onTextChanged)

        self.setWindowOpacity(0.0)
        screenGeometry = QApplication.primaryScreen().availableGeometry()
        self.targetX = (screenGeometry.width() - self.width()) // 2
        self.baseBottomY = screenGeometry.height() - 160

        self.adjustHeight(False)

        self.entryAnim = QParallelAnimationGroup(self)

        self.fadeIn = QPropertyAnimation(self, b"windowOpacity")
        self.fadeIn.setDuration(320)
        self.fadeIn.setStartValue(0.0)
        self.fadeIn.setEndValue(1.0)
        self.fadeIn.setEasingCurve(QEasingCurve.OutQuad)

        self.slideUp = QPropertyAnimation(self, b"pos")
        self.slideUp.setDuration(600)
        self.slideUp.setStartValue(QPoint(self.targetX, self.y() + 40))
        self.slideUp.setEndValue(QPoint(self.targetX, self.y()))
        self.slideUp.setEasingCurve(QEasingCurve.OutBack)

        self.entryAnim.addAnimation(self.fadeIn)
        self.entryAnim.addAnimation(self.slideUp)
        self.entryAnim.start(QAbstractAnimation.DeleteWhenStopped)

        self.containerAnim = QParallelAnimationGroup(self)
        self.bgAnim = QPropertyAnimation(self.container, b"bgColor", self)
        self.borderAnim = QPropertyAnimation(self.container, b"borderColor", self)
        self.indAnim = QPropertyAnimation(self.indicatorOpacity, b"opacity", self)

        self.bgAnim.setDuration(280)
        self.bgAnim.setEasingCurve(QEasingCurve.InOutSine)
        self.borderAnim.setDuration(280)
        self.borderAnim.setEasingCurve(QEasingCurve.InOutSine)
        self.indAnim.setDuration(280)
        self.indAnim.setEasingCurve(QEasingCurve.InOutSine)

        self.containerAnim.addAnimation(self.bgAnim)
        self.containerAnim.addAnimation(self.borderAnim)
        self.containerAnim.addAnimation(self.indAnim)

    def forceFocus(self):
        self.activateWindow()
        self.raise_()
        self.setFocus()
        self.inputField.setFocus()

    def onTextChanged(self):
        text = self.inputField.toPlainText().strip()
        hasText = bool(text)

        if hasText != self.isTypingMode:
            self.isTypingMode = hasText

            self.containerAnim.stop()

            if self.isTypingMode:
                self.bgAnim.setEndValue(QColor(8, 8, 10, int(255 * 0.96)))
                self.borderAnim.setEndValue(QColor(0, 240, 255, int(255 * 0.55)))
                self.indAnim.setEndValue(0.95)
            else:
                self.bgAnim.setEndValue(QColor(14, 14, 18, int(255 * 0.78)))
                self.borderAnim.setEndValue(QColor(255, 255, 255, int(255 * 0.15)))
                self.indAnim.setEndValue(0.04)

            self.containerAnim.start()

        self.adjustHeight(True)

    def adjustHeight(self, animate):
        docHeight = int(self.inputField.document().size().height())
        newTextHeight = max(28, min(docHeight, 160))

        self.inputField.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if docHeight > 160 else Qt.ScrollBarAlwaysOff)

        newWindowHeight = newTextHeight + 76

        if self.height() != newWindowHeight:
            newY = self.baseBottomY - newWindowHeight

            if animate and self.isVisible():
                if self.resizeAnimGroup:
                    if self.resizeAnimGroup.state() == QAbstractAnimation.Running:
                        self.resizeAnimGroup.stop()
                    self.resizeAnimGroup.deleteLater()

                self.resizeAnimGroup = QParallelAnimationGroup(self)

                winAnim = QPropertyAnimation(self, b"geometry", self)
                winAnim.setDuration(220)
                winAnim.setStartValue(self.geometry())
                winAnim.setEndValue(QRect(self.targetX, newY, self.width(), newWindowHeight))
                winAnim.setEasingCurve(QEasingCurve.OutQuart)

                txtMinAnim = QPropertyAnimation(self.inputField, b"minimumHeight", self)
                txtMinAnim.setDuration(220)
                txtMinAnim.setStartValue(self.inputField.height())
                txtMinAnim.setEndValue(newTextHeight)
                txtMinAnim.setEasingCurve(QEasingCurve.OutQuart)

                txtMaxAnim = QPropertyAnimation(self.inputField, b"maximumHeight", self)
                txtMaxAnim.setDuration(220)
                txtMaxAnim.setStartValue(self.inputField.height())
                txtMaxAnim.setEndValue(newTextHeight)
                txtMaxAnim.setEasingCurve(QEasingCurve.OutQuart)

                self.resizeAnimGroup.addAnimation(winAnim)
                self.resizeAnimGroup.addAnimation(txtMinAnim)
                self.resizeAnimGroup.addAnimation(txtMaxAnim)

                self.resizeAnimGroup.start()
            else:
                self.inputField.setMinimumHeight(newTextHeight)
                self.inputField.setMaximumHeight(newTextHeight)
                self.setGeometry(self.targetX, newY, self.width(), newWindowHeight)

    def triggerAccept(self):
        if self.isClosing: return
        self.isClosing = True
        self.commandText = self.inputField.toPlainText().strip()
        self.fadeOutAndClose(True)

    def triggerReject(self):
        if self.isClosing: return
        self.isClosing = True
        self.fadeOutAndClose(False)

    def fadeOutAndClose(self, isAccepting):
        self.outAnimGroup = QParallelAnimationGroup(self)

        fadeOut = QPropertyAnimation(self, b"windowOpacity")
        fadeOut.setDuration(220)
        fadeOut.setStartValue(self.windowOpacity())
        fadeOut.setEndValue(0.0)
        fadeOut.setEasingCurve(QEasingCurve.OutQuad)

        slideDown = QPropertyAnimation(self, b"pos")
        slideDown.setDuration(300)
        slideDown.setStartValue(self.pos())
        slideDown.setEndValue(QPoint(self.x(), self.y() + 25))
        slideDown.setEasingCurve(QEasingCurve.InBack)

        self.outAnimGroup.addAnimation(fadeOut)
        self.outAnimGroup.addAnimation(slideDown)

        if isAccepting:
            self.outAnimGroup.finished.connect(self.acceptDialog)
        else:
            self.outAnimGroup.finished.connect(self.rejectDialog)

        self.outAnimGroup.start()

    def acceptDialog(self):
        self.accept()

    def rejectDialog(self):
        self.reject()

    def getCommandText(self):
        return self.commandText

if __name__ == "__main__":
    app = QApplication(sys.argv)
    popup = InputPopup()
    popup.exec_()
    
    command = popup.getCommandText()
    if command:
        print(f"JARVIS_CMD:::{command}", flush=True)
    sys.exit(0)