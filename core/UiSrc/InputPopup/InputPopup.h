#ifndef INPUTPOPUP_H
#define INPUTPOPUP_H

#include <QDialog>
#include <QFrame>
#include <QTextEdit>
#include <QColor>
#include <QParallelAnimationGroup>
#include <QPropertyAnimation>
#include <QGraphicsOpacityEffect>
#include <QLabel>
#include <QVBoxLayout>
#include <QHBoxLayout>

class InputPopup; // Forward declaration

// ==========================================
// 💎 PREMIUM CUSTOM ANTIMALIASED CONTAINER
// ==========================================
class GlassContainer : public QFrame {
    Q_OBJECT
    Q_PROPERTY(QColor bgColor READ bgColor WRITE setBgColor)
    Q_PROPERTY(QColor borderColor READ borderColor WRITE setBorderColor)

public:
    explicit GlassContainer(QWidget *parent = nullptr);
    QColor bgColor() const;
    void setBgColor(const QColor &color);
    QColor borderColor() const;
    void setBorderColor(const QColor &color);

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    QColor m_bgColor;
    QColor m_borderColor;
};

// ==========================================
// 🧠 SMART TEXT FIELD (Minimal Scroll)
// ==========================================
class SmartInput : public QTextEdit {
    Q_OBJECT
public:
    explicit SmartInput(InputPopup *parentPopup, QWidget *parent = nullptr);

protected:
    void keyPressEvent(QKeyEvent *event) override;

private:
    InputPopup *m_parentPopup;
};

// ==========================================
// ⚡ ULTRA-PREMIUM MINIMAL INPUT CORE
// ==========================================
class InputPopup : public QDialog {
    Q_OBJECT

public:
    explicit InputPopup(QWidget *parent = nullptr);
    QString getCommandText() const;
    void triggerAccept();
    void triggerReject();

private slots:
    void onTextChanged();
    void forceFocus();
    void acceptDialog();
    void rejectDialog();

private:
    void initUI();
    void adjustHeight(bool animate = true);
    void fadeOutAndClose(bool isAccepting);

    QString commandText;
    bool isClosing;
    bool isTypingMode;
    int targetX;
    int baseBottomY;
    QString customFontFamily;

    GlassContainer *container;
    SmartInput *inputField;
    QLabel *iconLabel;
    QLabel *enterIndicator;
    QGraphicsOpacityEffect *indicatorOpacity;

    // 🔥 PRE-ALLOCATED ANIMATION POINTERS
    QParallelAnimationGroup *containerAnim;
    QPropertyAnimation *bgAnim;
    QPropertyAnimation *borderAnim;
    QPropertyAnimation *indAnim;

    // 🔥 NEW: Isko Group bana diya taaki window aur text sath mein stretch ho
    QParallelAnimationGroup *resizeAnimGroup;

    QParallelAnimationGroup *outAnimGroup;
};

#endif // INPUTPOPUP_H