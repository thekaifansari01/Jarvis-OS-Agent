#include "inputpopup.h"
#include <QPainter>
#include <QPainterPath>
#include <QKeyEvent>
#include <QApplication>
#include <QScreen>
#include <QFontDatabase>
#include <QTimer>
#include <QFile>

// ================== GlassContainer Implementation ==================
GlassContainer::GlassContainer(QWidget *parent) : QFrame(parent) {
    m_bgColor = QColor(14, 14, 18, (int)(255 * 0.78));
    m_borderColor = QColor(255, 255, 255, (int)(255 * 0.15));
}

QColor GlassContainer::bgColor() const { return m_bgColor; }
void GlassContainer::setBgColor(const QColor &color) {
    m_bgColor = color;
    update();
}

QColor GlassContainer::borderColor() const { return m_borderColor; }
void GlassContainer::setBorderColor(const QColor &color) {
    m_borderColor = color;
    update();
}

void GlassContainer::paintEvent(QPaintEvent *event) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    QLinearGradient bgGradient(0, 0, width(), height());
    int r = m_bgColor.red();
    int g = m_bgColor.green();
    int b = m_bgColor.blue();
    int a = m_bgColor.alpha();

    bgGradient.setColorAt(0.0, QColor(qMin(255, r + 20), qMin(255, g + 20), qMin(255, b + 25), a));
    bgGradient.setColorAt(0.5, m_bgColor);
    bgGradient.setColorAt(1.0, QColor(qMax(0, r - 8), qMax(0, g - 8), qMax(0, b - 10), qMin(255, a + 15)));

    QRect rect = this->rect().adjusted(2, 2, -2, -2);
    QPainterPath path;
    path.addRoundedRect(rect, 24, 24);

    painter.fillPath(path, bgGradient);

    QPainterPath innerHighlight;
    innerHighlight.addRoundedRect(rect.adjusted(1, 1, -1, -1), 23, 23);
    painter.setPen(QPen(QColor(255, 255, 255, 25), 1.0));
    painter.drawPath(innerHighlight);

    painter.setPen(QPen(m_borderColor, 1.5));
    painter.drawPath(path);
}

// ================== SmartInput Implementation ==================
SmartInput::SmartInput(InputPopup *parentPopup, QWidget *parent)
    : QTextEdit(parent), m_parentPopup(parentPopup) {
    setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    setAcceptRichText(false);
}

void SmartInput::keyPressEvent(QKeyEvent *event) {
    if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
        if (event->modifiers() & Qt::ShiftModifier) {
            QTextEdit::keyPressEvent(event);
        } else {
            m_parentPopup->triggerAccept();
        }
    } else if (event->key() == Qt::Key_Escape) {
        m_parentPopup->triggerReject();
    } else {
        QTextEdit::keyPressEvent(event);
    }
}

// ================== InputPopup Implementation ==================
InputPopup::InputPopup(QWidget *parent) : QDialog(parent), isClosing(false), isTypingMode(false) {

    // 🔥 CHANGED: Added ':/' to load font from Qt Resources
    int fontId = QFontDatabase::addApplicationFont(":/Data/fonts/english.ttf");
    if (fontId != -1) {
        customFontFamily = QFontDatabase::applicationFontFamilies(fontId).at(0);
    } else {
        customFontFamily = "Segoe UI";
    }

    containerAnim = nullptr;
    bgAnim = nullptr;
    borderAnim = nullptr;
    indAnim = nullptr;
    resizeAnimGroup = nullptr;
    outAnimGroup = nullptr;

    initUI();
    QTimer::singleShot(50, this, &InputPopup::forceFocus);
}

void InputPopup::initUI() {
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool);
    setAttribute(Qt::WA_TranslucentBackground, true);
    setFixedWidth(700);

    QVBoxLayout *outerLayout = new QVBoxLayout(this);
    outerLayout->setContentsMargins(25, 25, 25, 30);

    container = new GlassContainer(this);

    // 🔥 CHANGED: QGraphicsDropShadowEffect removed from here!

    QHBoxLayout *containerLayout = new QHBoxLayout(container);
    containerLayout->setContentsMargins(26, 18, 24, 18);
    containerLayout->setSpacing(18);
    containerLayout->setAlignment(Qt::AlignTop);

    iconLabel = new QLabel(container);
    // 🔥 CHANGED: Added ':/' to load image from Qt Resources
    QPixmap pixmap(":/Data/icons/jarvis_icon.png");
    if (!pixmap.isNull()) {
        iconLabel->setPixmap(pixmap.scaled(26, 26, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    } else {
        iconLabel->setText("⚡");
        iconLabel->setFont(QFont("Segoe UI Emoji", 16));
        iconLabel->setStyleSheet("color: rgba(255,255,255,0.75);");
    }
    iconLabel->setStyleSheet("background: transparent; margin-top: 0px;");
    containerLayout->addWidget(iconLabel, 0, Qt::AlignTop);

    inputField = new SmartInput(this, container);
    inputField->setPlaceholderText("What do you need?");
    inputField->setStyleSheet(QString(
                                  "QTextEdit { background: transparent; color: rgba(255, 255, 255, 0.98); border: none; "
                                  "font-family: \"%1\"; font-size: 17px; letter-spacing: 0.4px; "
                                  "selection-background-color: rgba(0, 240, 255, 0.35); selection-color: #FFFFFF; line-height: 1.6; }"
                                  "QTextEdit::placeholder { color: rgba(255, 255, 255, 0.22); font-weight: 300; }"
                                  ).arg(customFontFamily));
    containerLayout->addWidget(inputField);

    enterIndicator = new QLabel("↵", container);
    enterIndicator->setFont(QFont("Segoe UI", 20, QFont::Bold));
    enterIndicator->setStyleSheet("color: #00F0FF; background: transparent;");
    enterIndicator->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);

    indicatorOpacity = new QGraphicsOpacityEffect(enterIndicator);
    indicatorOpacity->setOpacity(0.04);
    enterIndicator->setGraphicsEffect(indicatorOpacity);
    containerLayout->addWidget(enterIndicator, 0, Qt::AlignTop);

    outerLayout->addWidget(container);

    connect(inputField, &QTextEdit::textChanged, this, &InputPopup::onTextChanged);

    setWindowOpacity(0.0);
    QRect screenGeometry = QApplication::primaryScreen()->availableGeometry();
    targetX = (screenGeometry.width() - width()) / 2;
    baseBottomY = screenGeometry.height() - 160;

    adjustHeight(false);

    QParallelAnimationGroup *entryAnim = new QParallelAnimationGroup(this);

    QPropertyAnimation *fadeIn = new QPropertyAnimation(this, "windowOpacity");
    fadeIn->setDuration(320);
    fadeIn->setStartValue(0.0);
    fadeIn->setEndValue(1.0);
    fadeIn->setEasingCurve(QEasingCurve::OutQuad);

    QPropertyAnimation *slideUp = new QPropertyAnimation(this, "pos");
    slideUp->setDuration(600);
    slideUp->setStartValue(QPoint(targetX, y() + 40));
    slideUp->setEndValue(QPoint(targetX, y()));
    slideUp->setEasingCurve(QEasingCurve::OutBack);

    entryAnim->addAnimation(fadeIn);
    entryAnim->addAnimation(slideUp);
    entryAnim->start(QAbstractAnimation::DeleteWhenStopped);

    containerAnim = new QParallelAnimationGroup(this);
    bgAnim = new QPropertyAnimation(container, "bgColor", this);
    borderAnim = new QPropertyAnimation(container, "borderColor", this);
    indAnim = new QPropertyAnimation(indicatorOpacity, "opacity", this);

    bgAnim->setDuration(280);
    bgAnim->setEasingCurve(QEasingCurve::InOutSine);
    borderAnim->setDuration(280);
    borderAnim->setEasingCurve(QEasingCurve::InOutSine);
    indAnim->setDuration(280);
    indAnim->setEasingCurve(QEasingCurve::InOutSine);

    containerAnim->addAnimation(bgAnim);
    containerAnim->addAnimation(borderAnim);
    containerAnim->addAnimation(indAnim);
}

void InputPopup::forceFocus() {
    activateWindow();
    raise();
    setFocus();
    inputField->setFocus();
}

void InputPopup::onTextChanged() {
    QString text = inputField->toPlainText().trimmed();
    bool hasText = !text.isEmpty();

    if (hasText != isTypingMode) {
        isTypingMode = hasText;

        containerAnim->stop();

        if (isTypingMode) {
            bgAnim->setEndValue(QColor(8, 8, 10, (int)(255 * 0.96)));
            borderAnim->setEndValue(QColor(0, 240, 255, (int)(255 * 0.55)));
            indAnim->setEndValue(0.95);
        } else {
            bgAnim->setEndValue(QColor(14, 14, 18, (int)(255 * 0.78)));
            borderAnim->setEndValue(QColor(255, 255, 255, (int)(255 * 0.15)));
            indAnim->setEndValue(0.04);
        }

        containerAnim->start();
    }

    adjustHeight(true);
}

void InputPopup::adjustHeight(bool animate) {
    int docHeight = (int)inputField->document()->size().height();
    int newTextHeight = qMax(28, qMin(docHeight, 160));

    inputField->setVerticalScrollBarPolicy(docHeight > 160 ? Qt::ScrollBarAsNeeded : Qt::ScrollBarAlwaysOff);

    int newWindowHeight = newTextHeight + 76;

    if (height() != newWindowHeight) {
        int newY = baseBottomY - newWindowHeight;

        if (animate && isVisible()) {

            if (resizeAnimGroup) {
                if (resizeAnimGroup->state() == QAbstractAnimation::Running) {
                    resizeAnimGroup->stop();
                }
                resizeAnimGroup->deleteLater();
            }

            resizeAnimGroup = new QParallelAnimationGroup(this);

            QPropertyAnimation *winAnim = new QPropertyAnimation(this, "geometry", this);
            winAnim->setDuration(220);
            winAnim->setStartValue(geometry());
            winAnim->setEndValue(QRect(targetX, newY, width(), newWindowHeight));
            winAnim->setEasingCurve(QEasingCurve::OutQuart);

            QPropertyAnimation *txtMinAnim = new QPropertyAnimation(inputField, "minimumHeight", this);
            txtMinAnim->setDuration(220);
            txtMinAnim->setStartValue(inputField->height());
            txtMinAnim->setEndValue(newTextHeight);
            txtMinAnim->setEasingCurve(QEasingCurve::OutQuart);

            QPropertyAnimation *txtMaxAnim = new QPropertyAnimation(inputField, "maximumHeight", this);
            txtMaxAnim->setDuration(220);
            txtMaxAnim->setStartValue(inputField->height());
            txtMaxAnim->setEndValue(newTextHeight);
            txtMaxAnim->setEasingCurve(QEasingCurve::OutQuart);

            resizeAnimGroup->addAnimation(winAnim);
            resizeAnimGroup->addAnimation(txtMinAnim);
            resizeAnimGroup->addAnimation(txtMaxAnim);

            resizeAnimGroup->start();

        } else {
            inputField->setMinimumHeight(newTextHeight);
            inputField->setMaximumHeight(newTextHeight);
            setGeometry(targetX, newY, width(), newWindowHeight);
        }
    }
}

void InputPopup::triggerAccept() {
    if (isClosing) return;
    isClosing = true;
    commandText = inputField->toPlainText().trimmed();
    fadeOutAndClose(true);
}

void InputPopup::triggerReject() {
    if (isClosing) return;
    isClosing = true;
    fadeOutAndClose(false);
}

void InputPopup::fadeOutAndClose(bool isAccepting) {
    outAnimGroup = new QParallelAnimationGroup(this);

    QPropertyAnimation *fadeOut = new QPropertyAnimation(this, "windowOpacity");
    fadeOut->setDuration(220);
    fadeOut->setStartValue(windowOpacity());
    fadeOut->setEndValue(0.0);
    fadeOut->setEasingCurve(QEasingCurve::OutQuad);

    QPropertyAnimation *slideDown = new QPropertyAnimation(this, "pos");
    slideDown->setDuration(300);
    slideDown->setStartValue(pos());
    slideDown->setEndValue(QPoint(x(), y() + 25));
    slideDown->setEasingCurve(QEasingCurve::InBack);

    outAnimGroup->addAnimation(fadeOut);
    outAnimGroup->addAnimation(slideDown);

    if (isAccepting) {
        connect(outAnimGroup, &QParallelAnimationGroup::finished, this, &InputPopup::acceptDialog);
    } else {
        connect(outAnimGroup, &QParallelAnimationGroup::finished, this, &InputPopup::rejectDialog);
    }

    outAnimGroup->start();
}

void InputPopup::acceptDialog() { QDialog::accept(); }
void InputPopup::rejectDialog() { QDialog::reject(); }

QString InputPopup::getCommandText() const { return commandText; }