import os
import sys
import json
import time

os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false;qt.text.font.db=false;default.warning=false"

from PyQt5.QtCore import Qt, QTimer, QObject, qInstallMessageHandler
from PyQt5.QtWidgets import QApplication

from PopupUI import TypingPopup

TYPING_STATUS_FILE = "Data/typing_status.json"
TTS_STATUS_FILE = "Data/tts_status.json"

TEST_CONTENT = """[excited] Bhai, yeh **popup ka premium test** hai — website previews ke saath.

## Streaming & Formatting

Yeh paragraph streaming test karta hai. **Bold** aur *italic*, `inline code`, aur multi-language code blocks.

### Python

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

### JavaScript

```javascript
const greet = (name) => `Hello, ${name}!`;
```

## Image Cards

Mountain landscape (picsum id 1015):

https://picsum.photos/id/1015/800/400

Pug dog (picsum id 1025):

https://picsum.photos/id/1025/800/400

Broken URL (error state test):

https://nonexistent-domain-xyz-12345.com/test.jpg

## YouTube Preview

https://www.youtube.com/watch?v=dQw4w9WgXcQ

## Website Previews

Bare URL — Wikipedia:

https://en.wikipedia.org/wiki/Artificial_intelligence

With display text — OpenAI:

[OpenAI](https://openai.com)

[GitHub](https://github.com)

[Anthropic](https://www.anthropic.com)

## Lists & Quote

1. First item
2. Second with **bold**
3. Third with *italic*

- Bullet one
- Bullet two

> Ek quote bhi — *premium feel matters*.

## Done

Sab test ho gaya. Website previews ab kaam karne chahiye.

Done."""


def suppress_qt_warnings(mode, context, message):
    suppressed = (
        "OpenType support missing",
        "QColor",
        "Unable to set geometry",
        "Resulting geometry",
        "QWindowsWindow::setGeometry",
    )
    if any(s in message for s in suppressed):
        return


qInstallMessageHandler(suppress_qt_warnings)


class TestDriver(QObject):
    def __init__(self, popup):
        super().__init__()
        self.popup = popup
        self.full_text = TEST_CONTENT
        self.pos = 0
        self.tick_counter = 0
        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self._stream_tick)

    def start(self):
        self._write_status("", "typing")
        QTimer.singleShot(600, self._begin)

    def _begin(self):
        print("[TEST] === Phase 1: Streaming started ===")
        self.stream_timer.start(65)

    def _stream_tick(self):
        self.tick_counter += 1
        if self.tick_counter % 9 == 0 and self.pos < len(self.full_text) // 2:
            return
        if self.pos >= len(self.full_text):
            self.stream_timer.stop()
            print("[TEST] === Phase 2: Stream complete ===")
            self._write_status(self.full_text, "completed")
            QTimer.singleShot(3500, self._start_tts)
            return
        base = 10
        if self.pos > len(self.full_text) * 0.6:
            base = 14
        end = self.pos + base
        while end < len(self.full_text) and self.full_text[end] not in " \n\t":
            end += 1
        end = min(end + 1, len(self.full_text))
        self.pos = end
        self._write_status(self.full_text[:self.pos], "typing")

    def _start_tts(self):
        print("[TEST] === Phase 3: TTS speaking simulated ===")
        self._write_tts(True, self.full_text[:200])
        QTimer.singleShot(5000, self._stop_tts)

    def _stop_tts(self):
        print("[TEST] === Phase 4: TTS stopped ===")
        self._write_tts(False, self.full_text[:200])
        QTimer.singleShot(800, self._final_close)

    def _final_close(self):
        print("[TEST] === Phase 5: Auto-closing popup ===")
        self.popup.fade_out(stop_tts=False)

    def _write_status(self, text, status):
        try:
            tmp = TYPING_STATUS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"text": text, "status": status}, f)
            os.replace(tmp, TYPING_STATUS_FILE)
        except Exception as e:
            print(f"[TEST] Write error: {e}")

    def _write_tts(self, speaking, text):
        try:
            tmp = TTS_STATUS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"speaking": speaking, "text": text}, f)
            os.replace(tmp, TTS_STATUS_FILE)
        except Exception as e:
            print(f"[TEST] TTS write error: {e}")


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    os.makedirs("Data", exist_ok=True)
    os.makedirs("Data/fonts", exist_ok=True)
    os.makedirs("Data/cache", exist_ok=True)

    with open(TYPING_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({"text": "", "status": "typing"}, f)

    app = QApplication(sys.argv)
    popup = TypingPopup()
    driver = TestDriver(popup)
    driver.start()

    print("[TEST] Popup launched. Website previews test.")
    print("[TEST] Interact: hover to keep open, ESC to close, click image card for preview.")
    print("[TEST] Streaming starts in 0.6s. Auto-closes after TTS phase.")

    sys.exit(app.exec_())