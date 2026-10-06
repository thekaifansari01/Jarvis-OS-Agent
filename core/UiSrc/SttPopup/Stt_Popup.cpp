#include "stt_popup.h"
#include <QRandomGenerator>

// ==========================================
// WAVEFORM INDICATOR
// ==========================================
WaveformIndicator::WaveformIndicator(QWidget *parent) : QWidget(parent) {
    setFixedSize(28, 18);
    bars = {3.0, 3.0, 3.0, 3.0};
    target_bars = {3.0, 3.0, 3.0, 3.0};
    is_animating = false;
    color = QColor("#0A84FF");

    anim_timer = new QTimer(this);
    connect(anim_timer, &QTimer::timeout, this, &WaveformIndicator::update_bars);
}

void WaveformIndicator::start_animation(const QString &color_hex) {
    color = QColor(color_hex);
    is_animating = true;
    anim_timer->start(8); // 120 FPS (1000ms / 120 = ~8ms)
}

void WaveformIndicator::stop_animation(const QString &color_hex) {
    color = QColor(color_hex);
    is_animating = false;
    target_bars = {4.0, 4.0, 4.0, 4.0};
}

void WaveformIndicator::update_bars() {
    if (is_animating) {
        for (int i = 0; i < 4; ++i) {
            if (std::abs(bars[i] - target_bars[i]) < 1.0) {
                target_bars[i] = QRandomGenerator::global()->bounded(3, 17);
            }
        }
    }

    bool needs_update = false;
    for (int i = 0; i < 4; ++i) {
        double diff = target_bars[i] - bars[i];
        if (std::abs(diff) > 0.1) {
            bars[i] += diff * 0.1; // Smooth factor for 120fps
            needs_update = true;
        }
    }

    if (needs_update || is_animating) {
        update();
    }
}

void WaveformIndicator::paintEvent(QPaintEvent *event) {
    Q_UNUSED(event);
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setPen(Qt::NoPen);
    painter.setBrush(color);

    int bar_width = 3;
    int spacing = 3;
    int start_x = (width() - (4 * bar_width + 3 * spacing)) / 2;

    for (int i = 0; i < 4; ++i) {
        int x = start_x + i * (bar_width + spacing);
        double height = bars[i];
        int y = (this->height() - height) / 2.0;
        painter.drawRoundedRect(x, y, bar_width, height, 1, 1);
    }
}

// ==========================================
// STT POPUP MAIN WINDOW (UDP LOGIC)
// ==========================================
STTPopup::STTPopup(QWidget *parent) : QWidget(parent), current_state("idle"), can_hide(true) {
    font_eng = QFont("Segoe UI", 13);
    // YAHAN PATH UPDATE KIYA HAI (:/ lagaya hai)
    int eng_id = QFontDatabase::addApplicationFont(":/Data/fonts/english.ttf");
    if (eng_id != -1) {
        QStringList fam = QFontDatabase::applicationFontFamilies(eng_id);
        if (!fam.isEmpty()) font_eng = QFont(fam.first(), 13);
    }

    font_hin = QFont("Nirmala UI", 14);
    // YAHAN PATH UPDATE KIYA HAI (:/ lagaya hai)
    int hin_id = QFontDatabase::addApplicationFont(":/Data/fonts/devangri.ttf");
    if (hin_id != -1) {
        QStringList fam = QFontDatabase::applicationFontFamilies(hin_id);
        if (!fam.isEmpty()) font_hin = QFont(fam.first(), 14);
    }

    resize_anim = new QPropertyAnimation(this, "geometry", this);
    resize_anim->setEasingCurve(QEasingCurve::OutExpo);
    resize_anim->setDuration(200);

    show_anim_group = new QParallelAnimationGroup(this);
    hide_anim_group = new QParallelAnimationGroup(this);

    transcribed_timer = new QTimer(this);
    transcribed_timer->setSingleShot(true);
    connect(transcribed_timer, &QTimer::timeout, this, &STTPopup::allow_hide);

    initUI();

    // ==========================================
    // UDP SOCKET INITIALIZATION
    // ==========================================
    udpSocket = new QUdpSocket(this);
    udpSocket->bind(QHostAddress::LocalHost, 5556); // Same port as Python
    connect(udpSocket, &QUdpSocket::readyRead, this, &STTPopup::readPendingDatagrams);

    QJsonObject initial_status;
    initial_status["status"] = "idle";
    initial_status["text"] = "";
    process_status_update(initial_status);
}

void STTPopup::readPendingDatagrams() {
    while (udpSocket->hasPendingDatagrams()) {
        QNetworkDatagram datagram = udpSocket->receiveDatagram();
        QByteArray data = datagram.data();

        QJsonDocument doc = QJsonDocument::fromJson(data);
        if (!doc.isNull() && doc.isObject()) {
            process_status_update(doc.object());
        }
    }
}

void STTPopup::initUI() {
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool | Qt::WindowTransparentForInput);
    setAttribute(Qt::WA_TranslucentBackground, true);
    setMinimumSize(1, 1);

    outer_layout = new QVBoxLayout(this);
    outer_layout->setContentsMargins(40, 40, 40, 40);

    island = new QFrame(this);
    island->setObjectName("Island");
    reset_island_style();
    island->setFixedHeight(48);

    shadow = new QGraphicsDropShadowEffect(this);
    shadow->setBlurRadius(30);
    shadow->setColor(QColor(0, 0, 0, 150));
    shadow->setOffset(0, 4);
    island->setGraphicsEffect(shadow);

    layout = new QHBoxLayout(island);
    layout->setContentsMargins(22, 0, 22, 0);
    layout->setSpacing(14);

    waveform = new WaveformIndicator(island);
    waveform->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);

    text_label = new QLabel("Listening...", island);
    text_label->setWordWrap(false);
    text_label->setSizePolicy(QSizePolicy::MinimumExpanding, QSizePolicy::MinimumExpanding);
    text_label->setAlignment(Qt::AlignVCenter | Qt::AlignLeft);

    set_fast_text_style("Listening...", "rgba(255, 255, 255, 0.5)", QFont::Normal);

    layout->addWidget(waveform, 0, Qt::AlignVCenter | Qt::AlignLeft);
    layout->addWidget(text_label, 1, Qt::AlignVCenter | Qt::AlignLeft);

    outer_layout->addWidget(island);
    setWindowOpacity(0.0);
    hide();
}

bool STTPopup::is_hindi(const QString &text) {
    QRegularExpression rx("[\\x{0900}-\\x{097F}]");
    return rx.match(text).hasMatch();
}

void STTPopup::set_fast_text_style(const QString &text, const QString &color, QFont::Weight weight) {
    QFont font = is_hindi(text) ? font_hin : font_eng;
    font.setWeight(weight);
    text_label->setFont(font);
    text_label->setStyleSheet(QString("color: %1; background: transparent; border: none;").arg(color));
    text_label->setText(text);
}

void STTPopup::reset_island_style() {
    island->setStyleSheet(
        "#Island {"
        "   background-color: #000000;"
        "   border: 1px solid rgba(255, 255, 255, 0.15);"
        "   border-radius: 24px;"
        "}"
        );
}

QRect STTPopup::calculate_target_geometry() {
    text_label->adjustSize();

    int island_width = text_label->sizeHint().width() + waveform->width() + 60;
    int ideal_width = qMax(200, qMin(island_width, 800)) + 80;
    int ideal_height = 48 + 80;

    QRect screen = QApplication::primaryScreen()->availableGeometry();
    int x = (screen.width() - ideal_width) / 2;
    int y = screen.bottom() - ideal_height - 50;

    return QRect(x, y, ideal_width, ideal_height);
}

void STTPopup::smooth_resize() {
    QRect new_geometry = calculate_target_geometry();
    if (target_geometry != new_geometry) {
        target_geometry = new_geometry;
        if (isVisible() && windowOpacity() > 0.8) {
            if (resize_anim->state() == QPropertyAnimation::Running) {
                resize_anim->stop();
            }
            resize_anim->setStartValue(geometry());
            resize_anim->setEndValue(new_geometry);
            resize_anim->start();
        } else {
            setGeometry(new_geometry);
        }
    }
}

void STTPopup::show_panel() {
    if (hide_anim_group->state() == QPropertyAnimation::Running) {
        hide_anim_group->stop();
    }

    smooth_resize();

    if (!isVisible() || windowOpacity() < 1.0) {
        int start_y = target_geometry.y() + 40;
        setGeometry(target_geometry.x(), start_y, target_geometry.width(), target_geometry.height());
        show();
        raise();

        show_anim_group->clear();
        QPropertyAnimation *fade_in = new QPropertyAnimation(this, "windowOpacity");
        fade_in->setDuration(200);
        fade_in->setStartValue(windowOpacity());
        fade_in->setEndValue(1.0);

        QPropertyAnimation *slide_up = new QPropertyAnimation(this, "pos");
        slide_up->setDuration(350);
        slide_up->setStartValue(pos());
        slide_up->setEndValue(QPoint(target_geometry.x(), target_geometry.y()));
        slide_up->setEasingCurve(QEasingCurve::OutBack);

        show_anim_group->addAnimation(fade_in);
        show_anim_group->addAnimation(slide_up);
        show_anim_group->start();
    }
}

void STTPopup::hide_panel() {
    if (!isVisible()) return;
    if (show_anim_group->state() == QPropertyAnimation::Running) {
        show_anim_group->stop();
    }

    hide_anim_group->clear();
    QPropertyAnimation *fade_out = new QPropertyAnimation(this, "windowOpacity");
    fade_out->setDuration(200);
    fade_out->setStartValue(windowOpacity());
    fade_out->setEndValue(0.0);

    QPropertyAnimation *slide_down = new QPropertyAnimation(this, "pos");
    slide_down->setDuration(250);
    slide_down->setStartValue(pos());
    slide_down->setEndValue(QPoint(x(), y() + 20));
    slide_down->setEasingCurve(QEasingCurve::InBack);

    hide_anim_group->addAnimation(fade_out);
    hide_anim_group->addAnimation(slide_down);

    disconnect(hide_anim_group, &QParallelAnimationGroup::finished, this, &STTPopup::hide_panel_finished);
    connect(hide_anim_group, &QParallelAnimationGroup::finished, this, &STTPopup::hide_panel_finished);

    hide_anim_group->start();
}

void STTPopup::hide_panel_finished() {
    hide();
}

void STTPopup::allow_hide() {
    can_hide = true;
    QJsonObject data;
    data["status"] = current_state;
    data["text"] = last_text;
    process_status_update(data);
}

void STTPopup::process_status_update(QJsonObject data) {
    current_state = data.value("status").toString("idle");
    QString text = data.value("text").toString("");

    if (current_state == "exit") {
        QApplication::quit();
        return;
    }

    if (current_state == "idle") {
        reset_island_style();
        waveform->stop_animation("#444444");
        if (!can_hide) return;
        hide_panel();
        last_text = "";
        return;
    }

    if (current_state == "listening" || current_state == "understanding") {
        reset_island_style();
        waveform->start_animation("#0A84FF");

        if (text.trimmed().isEmpty() && current_state == "listening") {
            set_fast_text_style("Listening...", "rgba(255, 255, 255, 0.4)", QFont::Normal);
        } else {
            QString display_text = text.trimmed().isEmpty() ? last_text : text;
            if (!is_hindi(display_text) && !display_text.isEmpty()) {
                display_text[0] = display_text[0].toUpper();
            }
            last_text = display_text;
            set_fast_text_style(last_text, "rgba(255, 255, 255, 0.95)", QFont::Medium);
        }
    } else if (current_state == "transcribed") {
        can_hide = false;
        transcribed_timer->start(2000);
        waveform->stop_animation("#32D74B");

        island->setStyleSheet(
            "#Island {"
            "   background-color: #000000;"
            "   border: 1px solid rgba(50, 215, 75, 0.5);"
            "   border-radius: 24px;"
            "}"
            );

        QString display_text = text.trimmed().isEmpty() ? last_text : text;
        if (!display_text.isEmpty() && !is_hindi(text)) {
            display_text[0] = display_text[0].toUpper();
        }
        set_fast_text_style(display_text, "#FFFFFF", QFont::Normal);
    }

    show_panel();
}