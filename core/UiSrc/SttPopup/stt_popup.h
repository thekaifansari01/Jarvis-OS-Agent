#ifndef STT_POPUP_H
#define STT_POPUP_H

#include <QWidget>
#include <QTimer>
#include <QPainter>
#include <QLabel>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QFrame>
#include <QGraphicsDropShadowEffect>
#include <QPropertyAnimation>
#include <QParallelAnimationGroup>
#include <QJsonObject>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QScreen>
#include <QApplication>
#include <QFontDatabase>
#include <QUdpSocket>
#include <QNetworkDatagram>

// Waveform Indicator Widget (120 FPS)
class WaveformIndicator : public QWidget {
    Q_OBJECT
public:
    explicit WaveformIndicator(QWidget *parent = nullptr);
    void start_animation(const QString &color_hex);
    void stop_animation(const QString &color_hex);

protected:
    void paintEvent(QPaintEvent *event) override;

private slots:
    void update_bars();

private:
    QList<double> bars;
    QList<double> target_bars;
    bool is_animating;
    QColor color;
    QTimer *anim_timer;
};

// Main Popup Window
class STTPopup : public QWidget {
    Q_OBJECT
public:
    explicit STTPopup(QWidget *parent = nullptr);

private slots:
    void readPendingDatagrams(); // UDP listener
    void process_status_update(QJsonObject data);
    void allow_hide();
    void hide_panel_finished();

private:
    void initUI();
    bool is_hindi(const QString &text);
    void set_fast_text_style(const QString &text, const QString &color, QFont::Weight weight);
    void reset_island_style();
    QRect calculate_target_geometry();
    void smooth_resize();
    void show_panel();
    void hide_panel();

    QFont font_eng;
    QFont font_hin;
    QString current_state;
    QRect target_geometry;
    QString last_text;
    bool can_hide;

    QVBoxLayout *outer_layout;
    QFrame *island;
    QHBoxLayout *layout;
    WaveformIndicator *waveform;
    QLabel *text_label;
    QGraphicsDropShadowEffect *shadow;

    QPropertyAnimation *resize_anim;
    QParallelAnimationGroup *show_anim_group;
    QParallelAnimationGroup *hide_anim_group;
    QTimer *transcribed_timer;

    QUdpSocket *udpSocket; // UDP Network object
};

#endif // STT_POPUP_H