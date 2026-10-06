#include "mainwindow.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFrame>
#include <QMouseEvent>
#include <QGraphicsDropShadowEffect>
#include <QPixmap>
#include <QFileInfo>
#include <QApplication>
#include <QFileDialog>
#include <QStandardPaths>
#include <QFile>

MainWindow::MainWindow(const QString &imagePath, const QString &title, const QString &description, QWidget *parent)
    : QMainWindow(parent), currentImagePath(imagePath)
{
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
    setAttribute(Qt::WA_TranslucentBackground);
    setFixedSize(540, 700);

    mainFrame = new QFrame(this);
    mainFrame->setGeometry(20, 20, 500, 660);
    mainFrame->setStyleSheet("QFrame#MainFrame { background-color: #050505; border-radius: 24px; border: 1px solid #1F1F1F; }");
    mainFrame->setObjectName("MainFrame");

    QGraphicsDropShadowEffect *shadow = new QGraphicsDropShadowEffect(this);
    shadow->setBlurRadius(40);
    shadow->setXOffset(0);
    shadow->setYOffset(15);
    shadow->setColor(QColor(0, 0, 0, 200));
    mainFrame->setGraphicsEffect(shadow);

    QVBoxLayout *layout = new QVBoxLayout(mainFrame);
    layout->setContentsMargins(30, 25, 30, 30);
    layout->setSpacing(15);

    QHBoxLayout *titleBar = new QHBoxLayout();
    QLabel *titleLabel = new QLabel(title.isEmpty() ? "JARVIS SYSTEM" : title.toUpper());
    titleLabel->setStyleSheet("color: #E5E5E5; font-family: 'Segoe UI', sans-serif; font-weight: 700; font-size: 13px; letter-spacing: 2px; background: transparent;");

    QPushButton *closeBtn = new QPushButton("✕");
    closeBtn->setFixedSize(28, 28);
    closeBtn->setCursor(Qt::PointingHandCursor);
    closeBtn->setStyleSheet("QPushButton { background-color: #111111; color: #737373; font-weight: bold; font-size: 12px; border-radius: 14px; border: none; } QPushButton:hover { background-color: #EF4444; color: #FFFFFF; }");
    connect(closeBtn, &QPushButton::clicked, this, &MainWindow::closeApp);

    titleBar->addWidget(titleLabel);
    titleBar->addStretch();
    titleBar->addWidget(closeBtn);
    layout->addLayout(titleBar);

    QLabel *subtitle = new QLabel(description.isEmpty() ? "Awaiting Visual Asset" : description);
    subtitle->setAlignment(Qt::AlignCenter);
    subtitle->setStyleSheet("color: #737373; font-family: 'Segoe UI', sans-serif; font-size: 14px; font-weight: 400; background: transparent;");
    layout->addWidget(subtitle);

    layout->addSpacing(10);

    QFrame *imageContainer = new QFrame();
    imageContainer->setMinimumSize(440, 440);
    imageContainer->setStyleSheet("QFrame { background-color: transparent; border-radius: 16px; border: none; }");

    QVBoxLayout *imgLayout = new QVBoxLayout(imageContainer);
    imgLayout->setContentsMargins(0, 0, 0, 0);

    imageLabel = new QLabel();
    imageLabel->setAlignment(Qt::AlignCenter);
    imageLabel->setStyleSheet("background: transparent; border: none;");

    opacityEffect = new QGraphicsOpacityEffect(this);
    imageLabel->setGraphicsEffect(opacityEffect);
    opacityEffect->setOpacity(0.0);

    fadeAnimation = new QPropertyAnimation(opacityEffect, "opacity", this);
    fadeAnimation->setDuration(500);
    fadeAnimation->setStartValue(0.0);
    fadeAnimation->setEndValue(1.0);
    fadeAnimation->setEasingCurve(QEasingCurve::OutCubic);

    imgLayout->addWidget(imageLabel);

    QHBoxLayout *centerImgLayout = new QHBoxLayout();
    centerImgLayout->addStretch();
    centerImgLayout->addWidget(imageContainer);
    centerImgLayout->addStretch();
    layout->addLayout(centerImgLayout);

    layout->addStretch();

    downloadBtn = new QPushButton("Download");
    downloadBtn->setFixedSize(180, 42);
    downloadBtn->setCursor(Qt::PointingHandCursor);
    downloadBtn->setStyleSheet("QPushButton { background-color: #FFFFFF; color: #000000; font-family: 'Segoe UI', sans-serif; font-size: 13px; font-weight: 600; border-radius: 21px; border: none; } QPushButton:hover { background-color: #E5E5E5; } QPushButton:disabled { background-color: #171717; color: #404040; }");
    downloadBtn->setDisabled(true);
    connect(downloadBtn, &QPushButton::clicked, this, &MainWindow::downloadImage);

    QHBoxLayout *btnLayout = new QHBoxLayout();
    btnLayout->addStretch();
    btnLayout->addWidget(downloadBtn);
    btnLayout->addStretch();
    layout->addLayout(btnLayout);

    statusLabel = new QLabel();
    statusLabel->setAlignment(Qt::AlignCenter);
    layout->addWidget(statusLabel);

    timer = new QTimer(this);
    connect(timer, &QTimer::timeout, this, &MainWindow::checkImageUpdate);
    timer->start(1000);

    if (!currentImagePath.isEmpty()) {
        checkImageUpdate();
    } else {
        imageLabel->setText("No Path Provided");
        imageLabel->setStyleSheet("color: #EF4444; font-weight: 500; font-family: 'Segoe UI', sans-serif; font-size: 14px; background: transparent;");
        opacityEffect->setOpacity(1.0);
        showToast("System Error", "#EF4444");
    }
}

MainWindow::~MainWindow() {}

void MainWindow::checkImageUpdate()
{
    if (currentImagePath.isEmpty()) return;

    QFileInfo fileInfo(currentImagePath);
    if (fileInfo.exists()) {
        QDateTime modTime = fileInfo.lastModified();
        if (modTime != lastModified) {
            QPixmap pixmap(currentImagePath);

            if (pixmap.isNull()) {
                return;
            }

            lastModified = modTime;
            imageLabel->setPixmap(pixmap.scaled(440, 440, Qt::KeepAspectRatio, Qt::SmoothTransformation));
            downloadBtn->setDisabled(false);

            opacityEffect->setOpacity(0.0);
            fadeAnimation->start();
            showToast("Asset Successfully Rendered", "#22C55E");
        }
    } else {
        lastModified = QDateTime();
        imageLabel->clear();
        imageLabel->setText("Awaiting Image Input...");
        imageLabel->setStyleSheet("color: #404040; font-weight: 500; font-family: 'Segoe UI', sans-serif; font-size: 14px; background: transparent;");
        opacityEffect->setOpacity(1.0);
        downloadBtn->setDisabled(true);
        showToast("Scanning environment...", "#737373");
    }
}

void MainWindow::downloadImage()
{
    setWindowFlag(Qt::WindowStaysOnTopHint, false);
    show();

    QString defaultPath = QStandardPaths::writableLocation(QStandardPaths::DownloadLocation) + "/JARVIS_Render_" + QDateTime::currentDateTime().toString("yyyyMMdd_HHmmss") + ".png";
    QString savePath = QFileDialog::getSaveFileName(this, "Save High-Res Image", defaultPath, "Images (*.png *.jpg *.jpeg)");

    setWindowFlag(Qt::WindowStaysOnTopHint, true);
    show();

    if (!savePath.isEmpty()) {
        if (QFile::exists(savePath)) {
            QFile::remove(savePath);
        }

        if (QFile::copy(currentImagePath, savePath)) {
            showToast("Saved to Local Drive", "#FFFFFF");
        } else {
            showToast("Error Securing Asset", "#EF4444");
        }
    }
}

void MainWindow::showToast(const QString &message, const QString &color)
{
    statusLabel->setText(message);
    statusLabel->setStyleSheet("color: " + color + "; font-family: 'Segoe UI', sans-serif; font-weight: 500; font-size: 12px; margin-top: 5px; background: transparent;");
}

void MainWindow::closeApp()
{
    QApplication::quit();
}

void MainWindow::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton) {
        dragPos = event->globalPosition().toPoint() - frameGeometry().topLeft();
        event->accept();
    }
}

void MainWindow::mouseMoveEvent(QMouseEvent *event)
{
    if (event->buttons() & Qt::LeftButton) {
        move(event->globalPosition().toPoint() - dragPos);
        event->accept();
    }
}