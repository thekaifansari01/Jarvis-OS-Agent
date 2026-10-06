import sys
from PyQt5.QtCore import qInstallMessageHandler
from PyQt5.QtWidgets import QApplication
from PopupUI import TypingPopup

def suppress_qt_warnings(mode, context, message):
    if "OpenType support missing" in message: pass
    elif "QColor" in message: pass 
    else: print(message)

if __name__ == "__main__":
    qInstallMessageHandler(suppress_qt_warnings)
    app = QApplication(sys.argv)
    
    popup = TypingPopup()
    
    sys.exit(app.exec_())