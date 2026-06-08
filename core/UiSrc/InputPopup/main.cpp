#include <QApplication>
#include <iostream>
#include "inputpopup.h"

int main(int argc, char *argv[]) {
    // Hide default warning logs matching your Python script
    qputenv("QT_LOGGING_RULES", "qt.qpa.window=false;default.warning=false");

    QApplication app(argc, argv);

    InputPopup popup;
    popup.exec(); // Modal dialog ki tarah run karega

    // C++ to Python IPC - Standard Output par dump marna
    QString command = popup.getCommandText();
    if (!command.isEmpty()) {
        // flush karne ke liye std::endl zaruri hai
        std::cout << "JARVIS_CMD:::" << command.toStdString() << std::endl;
    }

    return 0;
}