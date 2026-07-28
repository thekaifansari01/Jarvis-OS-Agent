#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QDateTime>
#include <QLabel>
#include <QPoint>
#include <QTimer>
#include <QPushButton>
#include <QGraphicsOpacityEffect>
#include <QPropertyAnimation>

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(const QString &imagePath,
               const QString &title,
               const QString &description,
               QWidget *parent = nullptr);
    ~MainWindow();

protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;

private slots:
    void checkImageUpdate();
    void closeApp();
    void downloadImage();
    void showToast(const QString &message, const QString &color);

private:
    QLabel *imageLabel;
    QLabel *statusLabel;
    QPushButton *downloadBtn;
    QString currentImagePath;
    QPoint dragPos;
    QTimer *timer;
    QDateTime lastModified;
    QGraphicsOpacityEffect *opacityEffect;
    QPropertyAnimation *fadeAnimation;
    QFrame *mainFrame;
};

#endif