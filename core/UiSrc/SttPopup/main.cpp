#include <QApplication>
#include "stt_popup.h"

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    STTPopup panel;
    return app.exec();
}