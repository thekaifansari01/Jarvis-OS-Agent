#include "mainwindow.h"
#include <QApplication>
#include <QCommandLineParser>

int main(int argc, char *argv[])
{
    QApplication a(argc, argv);
    QApplication::setApplicationName("JarvisPopup");
    QApplication::setApplicationVersion("1.0");

    QCommandLineParser parser;
    parser.setApplicationDescription("Universal Image Popup Engine for JARVIS");
    parser.addHelpOption();
    parser.addVersionOption();

    QCommandLineOption imageOption(QStringList() << "i" << "image", "Path to the image file.", "path");
    QCommandLineOption titleOption(QStringList() << "t" << "title", "Custom Title.", "text");
    QCommandLineOption descOption(QStringList() << "d" << "description", "Custom Description.", "text");

    parser.addOption(imageOption);
    parser.addOption(titleOption);
    parser.addOption(descOption);
    parser.process(a);

    QString imagePath = parser.value(imageOption);
    QString title = parser.value(titleOption);
    QString description = parser.value(descOption);

    MainWindow w(imagePath, title, description);
    w.show();

    return a.exec();
}