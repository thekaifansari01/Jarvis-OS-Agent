import sys
import os

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_TEST_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import time
import json
import socket
import pytest
from collections import deque
from unittest.mock import patch

if not os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

os.environ["QT_LOGGING_RULES"] = "qt.qpa.*=false;qt.text.font.db=false"

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer, QEventLoop, QPoint, QPointF, QEvent
from PyQt5.QtGui import QWheelEvent, QMouseEvent

from core.ui.AgentPanel.render.MarkdownRenderer import MarkdownRenderer
from core.ui.AgentPanel.widgets.ThoughtViewer import ThoughtViewer
from core.ui.AgentPanel.net.ZmqListener import AgentZmqListener
from core.ui.AgentPanel.widgets.StatusOrb import StatusOrb
from core.ui.AgentPanel.widgets.IslandContainer import IslandContainer
from core.ui.AgentPanel.widgets.ObservationCard import ObservationCard
from core.ui.AgentPanel.AgentPanel import AgentPanel
from core.ui.AgentPanel.core.Theme import (
    ACCENT_PALETTE, MOTION, SYNTAX_TOKENS, SURFACE_CODE_BG,
)
from core.ui.AgentPanel.core.FontRegistry import (
    get_ui_font, get_hindi_font, get_code_font, install_substitutions,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def _auto_qapp(qapp):
    return qapp


@pytest.fixture
def panel(qapp):
    with patch.object(AgentZmqListener, "start", lambda self: None), \
         patch.object(AgentZmqListener, "stop", lambda self: None):
        p = AgentPanel()
        yield p
        try:
            QApplication.instance().removeEventFilter(p)
        except Exception:
            pass
        p._cleanup_resources()
        p.close()
        p.deleteLater()
        QApplication.processEvents()


@pytest.fixture
def viewer(qapp):
    v = ThoughtViewer()
    v.resize(650, 500)
    yield v
    v.close()
    v.deleteLater()
    QApplication.processEvents()


@pytest.fixture
def orb(qapp):
    o = StatusOrb()
    yield o
    o.deleteLater()
    QApplication.processEvents()


@pytest.fixture
def island(qapp):
    c = IslandContainer()
    c.resize(600, 300)
    yield c
    c.deleteLater()
    QApplication.processEvents()


@pytest.fixture
def obs_card(qapp):
    card = ObservationCard()
    card.resize(400, 60)
    yield card
    card.deleteLater()
    QApplication.processEvents()


def _settle(ms=120):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def _port_available(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def _get_marked_blocks(doc):
    marked = []
    block = doc.begin()
    while block.isValid():
        bf = block.blockFormat()
        try:
            if bf.hasProperty(ThoughtViewer._CODE_MARKER_PROP) and \
               bool(bf.property(ThoughtViewer._CODE_MARKER_PROP)):
                marked.append(block)
        except Exception:
            pass
        block = block.next()
    return marked


def _make_mouse_move_event(x=50, y=50, buttons=Qt.NoButton):
    return QMouseEvent(
        QEvent.MouseMove,
        QPointF(x, y),
        buttons,
        buttons,
        Qt.NoModifier,
    )


class TestFontRegistry:

    def test_ui_font_returns_string(self):
        f = get_ui_font()
        assert isinstance(f, str) and len(f) > 0

    def test_hindi_font_returns_string(self):
        f = get_hindi_font()
        assert isinstance(f, str) and len(f) > 0

    def test_code_font_returns_string(self):
        f = get_code_font()
        assert isinstance(f, str) and len(f) > 0

    def test_install_substitutions_idempotent(self):
        install_substitutions()
        install_substitutions()
        install_substitutions()
        assert isinstance(get_ui_font(), str)

    def test_font_families_stable_across_calls(self):
        assert get_ui_font() == get_ui_font()
        assert get_hindi_font() == get_hindi_font()
        assert get_code_font() == get_code_font()


class TestTheme:

    def test_accent_palette_has_required_keys(self):
        required = [
            "search", "deep_task", "python", "thinking", "workspace",
            "communication", "gui", "mobile", "file_ops", "terminal",
            "memory", "calendar", "clipboard", "image_gen", "done",
            "idle", "error", "warning",
        ]
        for key in required:
            assert key in ACCENT_PALETTE, f"Missing accent key: {key}"

    def test_accent_palette_rgb_triplets(self):
        for key, val in ACCENT_PALETTE.items():
            assert isinstance(val, list) and len(val) == 3
            for c in val:
                assert 0 <= int(c) <= 255

    def test_motion_keys(self):
        for key in [
            "phase_increment", "resize_anim_ms", "fade_in_ms",
            "fade_out_ms", "thought_throttle_ms", "rgb_tick_ms",
            "resize_relayout_ms",
        ]:
            assert key in MOTION
            assert isinstance(MOTION[key], (int, float))

    def test_motion_phase_increment_range(self):
        assert 0.0 < MOTION["phase_increment"] < 0.2

    def test_syntax_tokens_keys(self):
        for key in ["comment", "string", "decorator", "keyword",
                    "builtin", "func", "number", "default"]:
            assert key in SYNTAX_TOKENS

    def test_surface_code_bg_marker(self):
        assert SURFACE_CODE_BG == "#0a0b10"

    def test_idle_color_updated(self):
        assert ACCENT_PALETTE["idle"] == [130, 140, 165]

    def test_image_gen_desaturated(self):
        assert ACCENT_PALETTE["image_gen"] == [240, 70, 100]


class TestMarkdownRenderer:

    def test_empty_input_returns_empty(self):
        assert MarkdownRenderer.to_html("", "Segoe UI", 12, [191, 90, 242]) == ""
        assert MarkdownRenderer.to_html("   \n\t  ", "Segoe UI", 12, [191, 90, 242]) == ""

    def test_plain_text_passes_through(self):
        html = MarkdownRenderer.to_html("Hello World", "Segoe UI", 12, [191, 90, 242])
        assert "Hello World" in html
        assert "<div" in html

    def test_headings_render(self):
        for level in (1, 2, 3, 4):
            html = MarkdownRenderer.to_html(
                f"{'#' * level} Header", "Segoe UI", 12, [255, 0, 0]
            )
            assert "Header" in html
            assert "font-weight: bold" in html

    def test_bold_italic_inline(self):
        html = MarkdownRenderer.to_html(
            "**bold** *italic* ***both***", "Segoe UI", 12, [255, 0, 0]
        )
        assert "<b" in html and "<i>" in html
        assert "bold" in html and "italic" in html

    def test_inline_code(self):
        html = MarkdownRenderer.to_html(
            "Use `print(x)` here", "Segoe UI", 12, [255, 0, 0]
        )
        assert "print(x)" in html
        assert "background-color: rgba(255, 255, 255, 0.11)" in html

    def test_links_render(self):
        html = MarkdownRenderer.to_html(
            "[Google](https://google.com)", "Segoe UI", 12, [255, 0, 0]
        )
        assert 'href="https://google.com"' in html
        assert ">Google<" in html

    def test_bullets_and_numbered(self):
        html = MarkdownRenderer.to_html(
            "- item A\n- item B\n1. first\n2. second",
            "Segoe UI", 12, [255, 0, 0],
        )
        assert "item A" in html and "item B" in html
        assert "1." in html and "2." in html

    def test_quote_block(self):
        html = MarkdownRenderer.to_html(
            "> wisdom here", "Segoe UI", 12, [255, 0, 0]
        )
        assert "wisdom here" in html
        assert "▎" in html

    def test_hr(self):
        html = MarkdownRenderer.to_html("---", "Segoe UI", 12, [255, 0, 0])
        assert "<hr" in html

    def test_auto_heal_unclosed_code_fence(self):
        html = MarkdownRenderer.to_html(
            "```python\nprint('x')", "Segoe UI", 12, [255, 0, 0]
        )
        assert "print" in html

    def test_code_block_no_table(self):
        html = MarkdownRenderer.to_html(
            "```python\nprint('hi')\n```", "Segoe UI", 12, [255, 0, 0]
        )
        assert "<table" not in html.lower()
        assert "</table>" not in html.lower()

    def test_code_block_bg_marker_present(self):
        html = MarkdownRenderer.to_html(
            "```python\nprint('hi')\n```", "Segoe UI", 12, [255, 0, 0]
        )
        assert SURFACE_CODE_BG in html.lower()
        assert "PYTHON" in html.upper()

    def test_code_block_uses_loaded_font(self):
        html = MarkdownRenderer.to_html(
            "```python\nprint('hi')\n```", "Segoe UI", 12, [255, 0, 0]
        )
        code_font = get_code_font()
        assert code_font in html

    def test_code_block_lang_label_uses_ui_font(self):
        ui_font = get_ui_font()
        html = MarkdownRenderer.to_html(
            "```python\nx = 1\n```", ui_font, 12, [255, 0, 0]
        )
        assert ui_font in html

    def test_code_block_no_zero_width_space(self):
        long_code = "x = '" + ("A" * 200) + "'"
        html = MarkdownRenderer.to_html(
            f"```python\n{long_code}\n```", "Segoe UI", 12, [255, 0, 0]
        )
        pre_start = html.find("<pre")
        pre_end = html.find("</pre>")
        assert pre_start != -1 and pre_end != -1
        code_section = html[pre_start:pre_end]
        assert "\u200b" not in code_section

    def test_highlight_cache_hits(self):
        MarkdownRenderer._highlight_cache.clear()
        code = "def foo(x):\n    return x + 1"
        r1 = MarkdownRenderer.highlight_code_cached(code)
        assert len(MarkdownRenderer._highlight_cache) == 1
        r2 = MarkdownRenderer.highlight_code_cached(code)
        assert r1 == r2
        assert len(MarkdownRenderer._highlight_cache) == 1

    def test_highlight_cache_bounds(self):
        MarkdownRenderer._highlight_cache.clear()
        for i in range(MarkdownRenderer._HIGHLIGHT_CACHE_LIMIT + 50):
            MarkdownRenderer.highlight_code_cached(f"x_{i} = {i}")
        assert len(MarkdownRenderer._highlight_cache) <= MarkdownRenderer._HIGHLIGHT_CACHE_LIMIT

    def test_html_cache_hits(self):
        MarkdownRenderer._html_cache.clear()
        md = "# Cache Test\nUnique line here 42"
        r1 = MarkdownRenderer.to_html(md, "Segoe UI", 12, [1, 2, 3])
        assert len(MarkdownRenderer._html_cache) == 1
        r2 = MarkdownRenderer.to_html(md, "Segoe UI", 12, [1, 2, 3])
        assert r1 == r2
        assert len(MarkdownRenderer._html_cache) == 1

    def test_html_cache_bounds(self):
        MarkdownRenderer._html_cache.clear()
        for i in range(MarkdownRenderer._HTML_CACHE_LIMIT + 50):
            MarkdownRenderer.to_html(f"text_{i}", "Segoe UI", 12, [1, 2, 3])
        assert len(MarkdownRenderer._html_cache) <= MarkdownRenderer._HTML_CACHE_LIMIT

    def test_html_cache_miss_on_accent_change(self):
        MarkdownRenderer._html_cache.clear()
        md = "accent test"
        MarkdownRenderer.to_html(md, "Segoe UI", 12, [255, 0, 0])
        MarkdownRenderer.to_html(md, "Segoe UI", 12, [0, 255, 0])
        assert len(MarkdownRenderer._html_cache) == 2

    def test_long_token_soft_wrap(self):
        token = "A" * 200
        html = MarkdownRenderer.to_html(token, "Segoe UI", 12, [255, 0, 0])
        assert "\u200b" in html

    def test_hindi_unicode_safe(self):
        html = MarkdownRenderer.to_html(
            "नमस्ते दुनिया, यह हिन्दी टेस्ट है।",
            "Nirmala UI", 13, [255, 0, 0],
        )
        assert "नमस्ते" in html

    def test_emoji_safe(self):
        html = MarkdownRenderer.to_html(
            "Test 🎉🚀✨ emoji", "Segoe UI", 12, [255, 0, 0]
        )
        assert "🎉" in html or "&#" in html

    def test_xss_script_escaped(self):
        html = MarkdownRenderer.to_html(
            "<script>alert('xss')</script>", "Segoe UI", 12, [255, 0, 0]
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_accent_rgb_clamped(self):
        html = MarkdownRenderer.to_html("hi", "Segoe UI", 12, [-999, 999, 555])
        assert "rgb(" in html
        assert "hi" in html

    def test_very_long_code_block(self):
        code = "\n".join(f"def f_{i}(): return {i}" for i in range(500))
        md = f"```python\n{code}\n```"
        t0 = time.perf_counter()
        html = MarkdownRenderer.to_html(md, "Segoe UI", 12, [255, 0, 0])
        dt = time.perf_counter() - t0
        assert "f_0" in html and "f_499" in html
        assert dt < 2.0

    def test_malformed_markdown(self):
        bad_inputs = [
            "***", "```", "```python", "> ", "#", "- ", "1. ",
            "[](url)", "[text]()", "\x00\x01", "\n\n\n",
            "**unclosed bold", "*unclosed italic",
            "`unclosed inline", "```\n```\n```",
        ]
        for bad in bad_inputs:
            try:
                MarkdownRenderer.to_html(bad, "Segoe UI", 12, [255, 0, 0])
            except Exception as e:
                pytest.fail(f"MarkdownRenderer crashed on {bad!r}: {e}")

    def test_hindi_inside_code_block(self):
        md = "```python\n# नमस्ते दुनिया\nprint(1)\n```"
        html = MarkdownRenderer.to_html(md, "Segoe UI", 12, [255, 0, 0])
        assert "नमस्ते" in html
        assert get_code_font() in html


class TestThoughtViewer:

    def test_empty_content_clears(self, viewer):
        viewer.set_markdown_content("", "Segoe UI", 12, [191, 90, 242])
        assert viewer.document().isEmpty() or viewer.document().toPlainText().strip() == ""

    def test_code_block_markers_applied(self, viewer):
        md = "```python\nprint('hello')\nprint('world')\n```"
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        marked = _get_marked_blocks(viewer.document())
        assert len(marked) >= 1
        texts = "".join(b.text() for b in marked)
        assert "print" in texts

    def test_code_block_bg_cleared(self, viewer):
        md = "```python\nprint('hi')\n```"
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        for b in _get_marked_blocks(viewer.document()):
            bg = b.blockFormat().background()
            assert bg.style() == Qt.NoBrush

    def test_render_cache_skips_same_input(self, viewer):
        md = "# Hello\nSome text"
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        key1 = viewer._last_render_key
        t0 = time.perf_counter()
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        dt = time.perf_counter() - t0
        assert viewer._last_render_key == key1
        assert dt < 0.02

    def test_render_cache_misses_on_change(self, viewer):
        viewer.set_markdown_content("a", "Segoe UI", 12, [191, 90, 242])
        viewer.set_markdown_content("b", "Segoe UI", 12, [191, 90, 242])
        assert "b" in viewer.document().toPlainText()

    def test_code_groups_cache_invalidated_on_set(self, viewer):
        viewer.set_markdown_content(
            "```python\nprint('x')\n```", "Segoe UI", 12, [191, 90, 242]
        )
        viewer._get_code_groups()
        assert viewer._code_groups_cache is not None
        viewer.set_markdown_content(
            "```python\nprint('y')\n```", "Segoe UI", 12, [191, 90, 242]
        )
        assert viewer._code_groups_cache is None

    def test_code_groups_cache_populated(self, viewer):
        md = "```python\nprint('x')\nprint('y')\n```"
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        groups = viewer._get_code_groups()
        assert isinstance(groups, list)
        assert len(groups) >= 1
        assert viewer._code_groups_cache is groups

    def test_rapid_updates_no_crash(self, viewer):
        base = "line " * 50
        for i in range(200):
            viewer.set_markdown_content(
                base + str(i), "Segoe UI", 12, [191, 90, 242]
            )
        _settle(50)
        assert not viewer.document().isEmpty()

    def test_streaming_code_block(self, viewer):
        lines = [f"x_{i} = {i}" for i in range(60)]
        full = "```python\n" + "\n".join(lines) + "\n```"
        for i in range(5, len(full), 15):
            viewer.set_markdown_content(full[:i], "Segoe UI", 12, [191, 90, 242])
        viewer.set_markdown_content(full, "Segoe UI", 12, [191, 90, 242])
        assert "x_59" in viewer.document().toPlainText()
        assert len(_get_marked_blocks(viewer.document())) >= 1

    def test_renders_without_paint_error(self, viewer):
        viewer.show()
        viewer.set_markdown_content(
            "```python\nprint('paint test')\n```",
            "Segoe UI", 12, [191, 90, 242],
        )
        _settle(50)
        pm = viewer.grab()
        assert not pm.isNull()
        assert pm.width() > 0 and pm.height() > 0
        viewer.hide()

    def test_scroll_follows_when_at_bottom(self, viewer):
        viewer.show()
        viewer.reset_scroll_lock()
        long_text = "\n".join(f"line {i}" for i in range(200))
        viewer.set_markdown_content(long_text, "Segoe UI", 12, [191, 90, 242])
        _settle(150)
        vb = viewer.verticalScrollBar()
        if vb.maximum() > 0:
            assert vb.value() >= vb.maximum() - 15

    def test_scroll_locks_when_user_scrolls_up(self, viewer):
        viewer.show()
        long_text = "\n".join(f"line {i}" for i in range(200))
        viewer.set_markdown_content(long_text, "Segoe UI", 12, [191, 90, 242])
        _settle(150)
        vb = viewer.verticalScrollBar()
        if vb.maximum() > 0:
            vb.setValue(0)
            viewer.user_scrolled_up = True
            prev = vb.value()
            viewer.set_markdown_content(
                long_text + "\nmore", "Segoe UI", 12, [191, 90, 242]
            )
            _settle(100)
            assert vb.value() <= prev + 5

    def test_wheel_event_no_crash(self, viewer):
        viewer.set_markdown_content(
            "\n".join(f"l{i}" for i in range(100)),
            "Segoe UI", 12, [191, 90, 242],
        )
        ev = QWheelEvent(
            QPointF(50, 50), QPointF(50, 50),
            QPoint(0, 0), QPoint(0, -120),
            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
        )
        try:
            viewer.wheelEvent(ev)
        except Exception as e:
            pytest.fail(f"wheelEvent crashed: {e}")


class TestStatusOrb:

    def test_construct_ok(self, orb):
        assert orb.width() == 24
        assert orb.height() == 24

    def test_set_state_updates_attrs(self, orb):
        orb.set_state([50, 215, 75], 1.2, "terminal")
        assert orb.mode == "terminal"
        assert orb.phase == 1.2

    def test_cacheable_mode_caches_icon(self, orb):
        orb.set_state([50, 215, 75], 0.5, "terminal")
        orb.grab()
        assert orb._cached_icon is not None
        assert orb._cached_icon_key is not None

    def test_uncacheable_mode_skips_cache(self, orb):
        orb.set_state([191, 90, 242], 0.5, "thinking")
        orb.grab()
        assert orb._cached_icon is None
        orb.set_state([130, 140, 165], 0.7, "idle")
        orb.grab()
        assert orb._cached_icon is None

    def test_cache_reused_on_same_bucket(self, orb):
        orb.set_state([50, 215, 75], 0.5, "terminal")
        orb.grab()
        key1 = orb._cached_icon_key
        icon1 = orb._cached_icon
        orb.set_state([51, 214, 74], 0.9, "terminal")
        orb.grab()
        assert orb._cached_icon_key == key1
        assert orb._cached_icon is icon1

    def test_cache_invalidated_on_mode_change(self, orb):
        orb.set_state([50, 215, 75], 0.5, "terminal")
        orb.grab()
        key1 = orb._cached_icon_key
        orb.set_state([50, 215, 75], 0.5, "python")
        orb.grab()
        assert orb._cached_icon_key != key1


class TestIslandContainer:

    def test_construct_ok(self, island):
        assert island.width() == 600
        assert island.height() == 300

    def test_update_visuals_does_not_crash(self, island):
        island.update_visuals([10, 132, 255], 1.5)
        island.grab()

    def test_static_pixmap_cached(self, island):
        island.update_visuals([10, 132, 255], 0.5)
        island.grab()
        assert island._static_pixmap is not None
        pm1 = island._static_pixmap
        island.grab()
        assert island._static_pixmap is pm1

    def test_static_pixmap_invalidated_on_size(self, island):
        island.update_visuals([10, 132, 255], 0.5)
        island.grab()
        pm1 = island._static_pixmap
        island.resize(700, 350)
        island.grab()
        assert island._static_pixmap is not pm1

    def test_rgb_bucket_grouping(self, island):
        island.rgb = [100, 150, 200]
        b1 = island._rgb_bucket()
        island.rgb = [101, 152, 199]
        b2 = island._rgb_bucket()
        assert b1 == b2

    def test_rgb_bucket_different_bucket(self, island):
        island.rgb = [10, 20, 30]
        b1 = island._rgb_bucket()
        island.rgb = [100, 150, 200]
        b2 = island._rgb_bucket()
        assert b1 != b2


class TestObservationCard:

    def test_construct_ok(self, obs_card):
        assert obs_card.width() == 400

    def test_set_accent_updates_rgb(self, obs_card):
        obs_card.set_accent([255, 0, 0])
        assert obs_card.rgb == [255, 0, 0]

    def test_paint_no_crash(self, obs_card):
        obs_card.set_accent([100, 200, 150])
        obs_card.show()
        _settle(30)
        pm = obs_card.grab()
        assert not pm.isNull()
        obs_card.hide()


@pytest.mark.skipif(
    not _port_available(5555) or not _port_available(5556) or not _port_available(5557),
    reason="ZMQ ports 5555/5556/5557 in use",
)
class TestAgentZmqListener:

    @pytest.fixture
    def listener(self, qapp):
        import zmq
        lst = AgentZmqListener()
        received = []
        lst.status_received.connect(lambda d: received.append(d))
        lst.start()
        _settle(500)
        yield lst, received, zmq
        lst.stop()
        time.sleep(0.2)

    def test_coalescing_burst(self, listener):
        lst, received, zmq = listener
        ctx = zmq.Context()
        pub = ctx.socket(zmq.PUB)
        pub.setsockopt(zmq.LINGER, 0)
        pub.bind("tcp://127.0.0.1:5555")
        _settle(400)

        for i in range(60):
            pub.send_string(
                "AGENT_UPDATE " + json.dumps({"step": i, "thought": f"t{i}"})
            )
        _settle(1200)

        assert 0 < len(received) < 60
        assert received[-1]["step"] >= 40

        pub.close()
        ctx.term()

    def test_confirmation_not_coalesced(self, listener):
        lst, _, zmq = listener
        received_confirms = []
        lst.confirmation_requested.connect(lambda d: received_confirms.append(d))

        ctx = zmq.Context()
        push = ctx.socket(zmq.PUSH)
        push.setsockopt(zmq.LINGER, 0)
        push.connect("tcp://127.0.0.1:5556")
        _settle(300)

        for i in range(3):
            push.send_json({"request_id": f"r{i}", "platform": "email"})
        _settle(1000)

        assert len(received_confirms) == 3

        push.close()
        ctx.term()

    def test_decision_send(self, listener):
        lst, _, zmq = listener
        ctx = zmq.Context()
        pull = ctx.socket(zmq.PULL)
        pull.setsockopt(zmq.LINGER, 0)
        pull.connect("tcp://127.0.0.1:5557")
        time.sleep(0.15)

        lst.send_decision({"request_id": "abc", "approved": True})
        poller = zmq.Poller()
        poller.register(pull, zmq.POLLIN)
        socks = dict(poller.poll(2000))
        assert pull in socks
        data = pull.recv_json()
        assert data["request_id"] == "abc" and data["approved"] is True

        pull.close()
        ctx.term()


class TestAgentPanel:

    def test_construct_no_crash(self, panel):
        assert panel is not None
        assert panel.status_tag.text() == "Jarvis Ready"
        assert not panel.isVisible()

    def test_max_thought_chars_reduced(self, panel):
        assert panel.MAX_THOUGHT_CHARS == 6000

    def test_confirm_queue_initialized(self, panel):
        assert isinstance(panel._confirm_queue, deque)
        assert len(panel._confirm_queue) == 0

    def test_resize_relayout_timer_exists(self, panel):
        assert panel._resize_relayout_timer is not None
        assert panel._resize_relayout_timer.isSingleShot()

    def test_cleaned_flag_starts_false(self, panel):
        assert panel._cleaned is False

    def test_process_status_basic(self, panel):
        panel.process_status_update({
            "step": 1,
            "action": "search_actions",
            "thought": "Hello",
            "tokens": 5,
            "action_detail": "reasoning",
            "observation": "test obs",
        })
        _settle(120)
        assert panel.current_step == 1
        assert panel.phase_label.text() == "Step 01"
        assert panel.detail_pill.isVisible()
        assert "reasoning" in panel.detail_pill.text()
        panel.process_status_update({
            "step": 2, "action": "THINKING",
            "thought": "planning", "tokens": 8,
            "action_detail": "internal",
        })
        _settle(120)
        assert panel.detail_pill.isHidden()

    def test_task_complete_triggers_hide(self, panel):
        panel.process_status_update({
            "step": 1, "action": "THINKING",
            "thought": "working", "tokens": 10,
        })
        _settle(80)
        panel.process_status_update({
            "step": 0, "action": "", "thought": "", "tokens": 100,
        })
        _settle(80)
        assert panel.current_action_type == "done"
        assert panel.status_tag.text() == "Task Completed"
        assert panel.hide_timer.isActive()

    def test_final_thought_flushed_on_complete(self, panel):
        panel.process_status_update({
            "step": 1, "action": "THINKING",
            "thought": "working", "tokens": 5,
        })
        _settle(150)
        panel.process_status_update({
            "step": 0, "action": "",
            "thought": "FINAL SUMMARY TEXT",
            "tokens": 100,
        })
        _settle(150)
        assert "FINAL SUMMARY TEXT" in panel._current_thought_text
        assert "FINAL SUMMARY TEXT" in panel.thought_viewer.document().toPlainText()

    def test_long_thought_truncation(self, panel):
        huge = "x" * (panel.MAX_THOUGHT_CHARS + 5000)
        panel.process_status_update({
            "step": 1, "action": "THINKING", "thought": huge, "tokens": 5000,
        })
        panel.flush_pending_thought()
        assert len(panel._current_thought_text) <= panel.MAX_THOUGHT_CHARS + 20

    def test_action_mapping(self, panel):
        cases = {
            "search_actions": "search",
            "deep_research": "deep_task",
            "run_python_code": "python",
            "execute_terminal_command": "terminal",
            "ABORT": "deep_task",
        }
        for raw, expect_type in cases.items():
            _, t = panel.resolve_action_display(raw)
            assert t == expect_type

    def test_action_mapping_unknown(self, panel):
        label, t = panel.resolve_action_display("custom_thing")
        assert t == "thinking"
        assert "Custom Thing" in label

    def test_confirmation_flow_full(self, panel):
        panel.show_confirmation_preview({
            "request_id": "req-1",
            "platform": "email",
            "to": "test@example.com",
            "subject": "Hello",
            "body": "Test message",
            "attachments": ["a.pdf"],
        })
        _settle(120)
        assert panel.awaiting_confirmation
        assert panel.preview_card.isVisible()
        assert panel.active_confirm_id == "req-1"
        assert panel.preview_subject_input.isVisible()

        panel.handle_confirm_decision(True)
        _settle(80)
        assert not panel.awaiting_confirmation
        assert panel.preview_card.isHidden()

    def test_confirmation_cancel(self, panel):
        panel.show_confirmation_preview({
            "request_id": "req-2",
            "platform": "whatsapp",
            "to": "+1", "body": "hi", "subject": "",
        })
        _settle(80)
        panel.handle_confirm_decision(False)
        _settle(80)
        assert not panel.awaiting_confirmation
        assert panel.current_action_type == "idle"

    def test_whatsapp_no_subject_input(self, panel):
        panel.show_confirmation_preview({
            "request_id": "wa", "platform": "whatsapp",
            "to": "+91", "body": "hi", "subject": "",
        })
        _settle(80)
        assert not panel.preview_subject_input.isVisible()

    def test_confirmation_queue_serializes(self, panel):
        panel.show_confirmation_preview({
            "request_id": "r1", "platform": "email",
            "to": "a@b.c", "body": "b1", "subject": "s1",
        })
        _settle(80)
        panel.show_confirmation_preview({
            "request_id": "r2", "platform": "email",
            "to": "a@b.c", "body": "b2", "subject": "s2",
        })
        _settle(80)
        assert panel.active_confirm_id == "r1"
        assert len(panel._confirm_queue) == 1

        panel.handle_confirm_decision(True)
        _settle(120)
        assert panel.active_confirm_id == "r2"
        assert len(panel._confirm_queue) == 0

        panel.handle_confirm_decision(True)
        _settle(120)
        assert not panel.awaiting_confirmation

    def test_confirmation_queue_three_items(self, panel):
        for i in range(3):
            panel.show_confirmation_preview({
                "request_id": f"q{i}", "platform": "email",
                "to": "a@b.c", "body": f"b{i}", "subject": f"s{i}",
            })
            _settle(40)
        assert len(panel._confirm_queue) == 2
        for expected in ["q0", "q1", "q2"]:
            assert panel.active_confirm_id == expected
            panel.handle_confirm_decision(False)
            _settle(120)
        assert not panel.awaiting_confirmation

    def test_preview_body_uses_document_default_font(self, panel):
        panel.show_confirmation_preview({
            "request_id": "font-test", "platform": "email",
            "to": "x@y.z", "subject": "s", "body": "test body content",
        })
        _settle(80)
        doc_font = panel.preview_body_edit.document().defaultFont()
        assert doc_font.family() != ""
        panel.handle_confirm_decision(False)
        _settle(60)

    def test_show_panel_idempotent(self, panel):
        panel.show_panel()
        _settle(400)
        g1 = panel.geometry()
        panel.show_panel()
        _settle(80)
        g2 = panel.geometry()
        assert g1 == g2

    def test_hide_stops_timer(self, panel):
        panel.show_panel()
        _settle(400)
        assert panel.rgb_timer.isActive()
        panel.hide_panel()
        _settle(400)
        assert not panel.rgb_timer.isActive()

    def test_resize_no_crash(self, panel):
        panel.show_panel()
        _settle(400)
        panel.resize_edge = "bottom_right"
        panel.resize_start_mouse = QPoint(0, 0)
        panel.resize_start_geom = panel.geometry()
        panel.perform_interactive_resize(QPoint(80, 80))
        _settle(80)
        assert panel.width() > 0 and panel.height() > 0

    def test_reset_default_size(self, panel):
        panel.show_panel()
        _settle(400)
        panel.user_width = 900
        panel.user_height = 500
        panel._user_resized = True
        panel.reset_to_default_size()
        _settle(400)
        assert panel.user_width == panel.DEFAULT_WIDTH
        assert panel.user_height == panel.DEFAULT_HEIGHT

    def test_status_duplicate_ignored(self, panel):
        status = {"step": 1, "action": "THINKING", "thought": "x", "tokens": 1}
        panel.process_status_update(status)
        _settle(80)
        panel.last_status = status
        panel.process_status_update(status)
        _settle(30)

    def test_cleanup_idempotent(self, panel):
        panel._cleanup_resources()
        panel._cleanup_resources()
        panel._cleanup_resources()
        assert panel._cleaned is True

    def test_stuck_drag_reset_via_eventfilter(self, panel):
        panel.show_panel()
        _settle(400)
        panel.is_dragging = True
        panel._interaction_origin = QPoint(0, 0)
        panel.drag_position = QPoint(10, 10)
        ev = _make_mouse_move_event(80, 80, Qt.NoButton)
        panel.eventFilter(panel, ev)
        assert not panel.is_dragging
        assert not hasattr(panel, "drag_position")

    def test_stuck_resize_reset_via_eventfilter(self, panel):
        panel.show_panel()
        _settle(400)
        panel.is_resizing = True
        panel.resize_edge = "bottom_right"
        panel._interaction_origin = QPoint(0, 0)
        ev = _make_mouse_move_event(80, 80, Qt.NoButton)
        panel.eventFilter(panel, ev)
        assert not panel.is_resizing
        assert panel.resize_edge is None

    def test_off_screen_custom_pos_recovery(self, panel):
        panel.custom_pos = QPoint(-99999, -99999)
        geom = panel.calculate_target_geometry()
        assert panel.custom_pos is None
        assert geom.x() >= 0


class TestRegressionGuards:

    def test_regression_01_zmq_coalescing_logic(self):
        import inspect
        src = inspect.getsource(AgentZmqListener.run)
        assert "latest_data" in src
        assert "if latest_data is not None:" in src

    def test_regression_01_drain_capped(self):
        import inspect
        src = inspect.getsource(AgentZmqListener.run)
        assert "range(100)" in src

    def test_regression_02_sync_does_not_flush(self, panel):
        panel._pending_thought_text = "PENDING_SENTINEL"
        panel._current_thought_text = "CURRENT"
        panel.sync_thought_viewer_height(panel.user_width)
        assert panel._pending_thought_text == "PENDING_SENTINEL"

    def test_regression_02_render_throttled(self, panel):
        render_count = [0]
        orig_render = panel.render_thought_now
        def counting_render():
            render_count[0] += 1
            orig_render()
        panel.render_thought_now = counting_render

        for i in range(100):
            panel.process_status_update({
                "step": 1, "action": "THINKING",
                "thought": f"t{i}" * 50, "tokens": i,
            })
        assert render_count[0] < 50

    def test_regression_02_throttle_interval(self, panel):
        assert panel.thought_render_timer.interval() == MOTION["thought_throttle_ms"]

    def test_regression_03_highlight_cache_used(self):
        MarkdownRenderer._highlight_cache.clear()
        code = "x = 1\ny = 2\nz = x + y"
        MarkdownRenderer.highlight_code_cached(code)
        first_size = len(MarkdownRenderer._highlight_cache)
        MarkdownRenderer.highlight_code_cached(code)
        assert len(MarkdownRenderer._highlight_cache) == first_size

    def test_regression_03_full_text_cache(self, viewer):
        md = "# Title\n- a\n- b"
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        k1 = viewer._last_render_key
        t0 = time.perf_counter()
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        dt = time.perf_counter() - t0
        assert viewer._last_render_key == k1
        assert dt < 0.015

    def test_regression_04_no_table(self):
        html = MarkdownRenderer.to_html(
            "```\nfoo\n```", "Segoe UI", 12, [191, 90, 242]
        )
        assert "<table" not in html.lower()

    def test_regression_04_markers_present(self, viewer):
        viewer.set_markdown_content(
            "```python\nprint('x')\n```", "Segoe UI", 12, [191, 90, 242]
        )
        assert len(_get_marked_blocks(viewer.document())) >= 1

    def test_regression_05_height_cache(self, panel):
        panel._current_thought_text = "line\n" * 50
        panel._invalidate_height_cache()
        h1 = panel.sync_thought_viewer_height(panel.user_width)
        assert panel._last_sync_height > 0
        t0 = time.perf_counter()
        h2 = panel.sync_thought_viewer_height(panel.user_width)
        dt = time.perf_counter() - t0
        assert h1 == h2
        assert dt < 0.01

    def test_regression_05_max_height_lock(self, panel):
        panel._current_thought_text = "line\n" * 2000
        panel.render_thought_now()
        panel._invalidate_height_cache()
        panel.sync_thought_viewer_height(panel.user_width)
        assert panel._viewer_at_max_height

        t0 = time.perf_counter()
        for _ in range(100):
            panel.sync_thought_viewer_height(panel.user_width)
        dt = time.perf_counter() - t0
        assert dt < 0.2

    def test_regression_06_rgb_timer_lifecycle(self, panel):
        panel.show_panel()
        _settle(400)
        assert panel.rgb_timer.isActive()
        panel.hide_panel()
        _settle(400)
        assert not panel.rgb_timer.isActive()

    def test_regression_06_timer_restarts_on_show(self, panel):
        panel.hide_panel()
        _settle(400)
        panel.show_panel()
        _settle(400)
        assert panel.rgb_timer.isActive()

    def test_regression_07_max_thought_chars_capped(self, panel):
        assert panel.MAX_THOUGHT_CHARS <= 8000

    def test_regression_08_zws_not_in_code(self):
        long_str = "x" * 200
        md = f"```python\nval = '{long_str}'\n```"
        html = MarkdownRenderer.to_html(md, "Segoe UI", 12, [255, 0, 0])
        pre_start = html.find("<pre")
        pre_end = html.find("</pre>")
        assert pre_start != -1
        assert "\u200b" not in html[pre_start:pre_end]


class TestStress:

    def test_stream_1000_tokens(self, panel):
        t0 = time.perf_counter()
        for i in range(1000):
            panel.process_status_update({
                "step": 1,
                "action": "THINKING",
                "thought": ("thinking text " * 5) + str(i),
                "tokens": i * 10,
            })
        dt = time.perf_counter() - t0
        assert dt < 3.0

    def test_stream_with_event_loop(self, panel):
        t0 = time.perf_counter()
        base = "Reasoning: " * 20
        for i in range(200):
            panel.process_status_update({
                "step": 1,
                "action": "THINKING",
                "thought": base + str(i),
                "tokens": i,
            })
            if i % 10 == 0:
                QApplication.processEvents()
        dt = time.perf_counter() - t0
        assert dt < 5.0

    def test_stream_10kb_code_block(self, panel):
        code = "\n".join(f"x_{i} = {i} * 2" for i in range(500))
        full = "```python\n" + code + "\n```"
        chunks = [full[i:i + 100] for i in range(0, len(full), 100)]

        t0 = time.perf_counter()
        for i, _chunk in enumerate(chunks):
            panel.process_status_update({
                "step": 1,
                "action": "THINKING",
                "thought": full[:min(len(full), (i + 1) * 100)],
                "tokens": (i + 1) * 30,
            })
        dt = time.perf_counter() - t0
        assert dt < 5.0

        panel.flush_pending_thought()
        _settle(80)
        assert "x_499" in panel.thought_viewer.document().toPlainText()

    def test_stream_hindi_heavy(self, panel):
        hindi = "यह एक परीक्षण है जो हिन्दी टेक्स्ट को स्ट्रीम करता है। " * 50
        for i in range(100):
            panel.process_status_update({
                "step": 1, "action": "THINKING",
                "thought": hindi[:i * 20], "tokens": i * 10,
            })
        panel.flush_pending_thought()
        _settle(80)
        assert panel.thought_viewer.document().blockCount() > 0

    def test_stream_emoji(self, panel):
        emoji = "🚀🎉✨🔥💯" * 100
        for i in range(50):
            panel.process_status_update({
                "step": 1, "action": "THINKING",
                "thought": emoji[:i * 5], "tokens": i,
            })
        panel.flush_pending_thought()
        _settle(50)

    def test_many_code_blocks(self, viewer):
        md_parts = []
        for i in range(20):
            md_parts.append(f"### Block {i}\n")
            md_parts.append(f"```python\ndef f_{i}():\n    return {i}\n```\n")
        md = "".join(md_parts)
        viewer.set_markdown_content(md, "Segoe UI", 12, [191, 90, 242])
        marked = _get_marked_blocks(viewer.document())
        assert len(marked) >= 20

    def test_single_giant_token(self, viewer):
        giant = "A" * 5000
        viewer.set_markdown_content(giant, "Segoe UI", 12, [191, 90, 242])
        doc = viewer.document()
        doc.setTextWidth(500)
        assert doc.size().height() > 100

    def test_rapid_hide_show_cycles(self, panel):
        for _ in range(20):
            panel.show_panel()
            QApplication.processEvents()
            panel.hide_panel()
            _settle(60)
        _settle(400)
        assert not panel.rgb_timer.isActive()
        assert not panel.hide_timer.isActive()


class TestGlitch:

    def test_malformed_status_no_crash(self, panel):
        bad_packets = [
            {},
            {"step": 1},
            {"thought": None, "tokens": None},
            {"step": "1", "action": 42},
            {"observation": "", "action_detail": ""},
            {"thought": "\x00\x01\x02", "tokens": -5},
            {"step": -1, "action": None},
            {"step": 0, "action": "idle", "thought": "Initialized"},
        ]
        for pkt in bad_packets:
            try:
                panel.process_status_update(pkt)
                QApplication.processEvents()
            except Exception as e:
                pytest.fail(f"Crashed on {pkt}: {type(e).__name__}: {e}")

    def test_confirm_missing_fields(self, panel):
        try:
            panel.show_confirmation_preview({"request_id": "x"})
            _settle(80)
            panel.handle_confirm_decision(False)
            _settle(50)
        except Exception as e:
            pytest.fail(f"Confirm crashed: {e}")

    def test_confirm_empty_attachments(self, panel):
        panel.show_confirmation_preview({
            "request_id": "e", "platform": "email",
            "to": "a@b.c", "subject": "s", "body": "b",
            "attachments": [],
        })
        _settle(80)
        assert not panel.preview_attachment_label.isVisible()

    def test_decision_without_awaiting(self, panel):
        panel.handle_confirm_decision(True)
        panel.handle_confirm_decision(False)

    def test_rgb_timer_idempotent(self, panel):
        panel.start_pulse_animation()
        panel.start_pulse_animation()
        panel.start_pulse_animation()
        assert panel.rgb_timer.isActive()

    def test_empty_thought_clears_viewer(self, panel):
        panel.process_status_update({
            "step": 1, "action": "THINKING", "thought": "hello", "tokens": 1,
        })
        panel.flush_pending_thought()
        _settle(50)
        panel.process_status_update({
            "step": 1, "action": "THINKING", "thought": "", "tokens": 2,
        })
        panel.flush_pending_thought()
        _settle(50)
        assert panel._current_thought_text == ""

    def test_queue_survives_cancel_chain(self, panel):
        for i in range(3):
            panel.show_confirmation_preview({
                "request_id": f"cc{i}", "platform": "email",
                "to": "a@b.c", "body": f"b{i}", "subject": f"s{i}",
            })
            _settle(40)
        for _ in range(3):
            panel.handle_confirm_decision(False)
            _settle(100)
        assert not panel.awaiting_confirmation
        assert len(panel._confirm_queue) == 0


class TestPerformance:

    def test_single_call_no_freeze(self, panel):
        base = "text " * 500
        slowest = 0.0
        for i in range(50):
            t0 = time.perf_counter()
            panel.process_status_update({
                "step": 1, "action": "THINKING",
                "thought": base + str(i), "tokens": i * 20,
            })
            dt = (time.perf_counter() - t0) * 1000
            slowest = max(slowest, dt)
        assert slowest < 100

    def test_markdown_render_small_fast(self):
        t0 = time.perf_counter()
        for _ in range(100):
            MarkdownRenderer.to_html("# Hi\nText", "Segoe UI", 12, [255, 0, 0])
        dt = time.perf_counter() - t0
        assert dt < 0.5

    def test_markdown_render_large_acceptable(self):
        body = "\n".join(
            f"Line {i} with **bold** and `code`" for i in range(200)
        )
        t0 = time.perf_counter()
        MarkdownRenderer.to_html(body, "Segoe UI", 12, [255, 0, 0])
        dt = time.perf_counter() - t0
        assert dt < 2.0

    def test_cache_speedup_measurable(self):
        code = "\n".join(f"def f_{i}(): return {i}" for i in range(100))
        MarkdownRenderer._highlight_cache.clear()

        t0 = time.perf_counter()
        MarkdownRenderer.highlight_code_cached(code)
        cold = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(20):
            MarkdownRenderer.highlight_code_cached(code)
        warm = (time.perf_counter() - t0) / 20

        assert warm < cold

    def test_html_cache_speedup(self):
        MarkdownRenderer._html_cache.clear()
        md = "# Speed Test\n" + "\n".join(f"Line {i}" for i in range(50))

        t0 = time.perf_counter()
        MarkdownRenderer.to_html(md, "Segoe UI", 12, [255, 0, 0])
        cold = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(50):
            MarkdownRenderer.to_html(md, "Segoe UI", 12, [255, 0, 0])
        warm = (time.perf_counter() - t0) / 50

        assert warm < cold


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s", "--tb=short"]))