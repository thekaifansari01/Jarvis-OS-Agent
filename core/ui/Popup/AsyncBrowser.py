import html as html_lib
import json
import math
import os
import re
import time
import base64
import urllib.parse
from collections import OrderedDict
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtCore import Qt, QUrl, QTimer, QRectF, QPointF, QByteArray
from PyQt5.QtWidgets import QTextBrowser, QFrame, QSizePolicy, QApplication
from PyQt5.QtGui import (
    QColor, QImage, QPainter, QPainterPath, QPen,
    QTextDocument, QPalette, QDesktopServices, QFont,
    QFontMetrics, QLinearGradient, QTextBlockFormat, QTextCursor
)
from PyQt5.QtSvg import QSvgRenderer


def _decode_resource_payload(encoded):
    try:
        s = str(encoded or "")
        padded = s + ("=" * (-len(s) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def _encode_resource_payload(url):
    try:
        raw = str(url or "").encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    except Exception:
        return ""


class AsyncTextBrowser(QTextBrowser):
    CARD_W = 656
    CARD_H = 316
    IMG_W = 656
    IMG_H = 308

    USER_AGENT = (
        b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        b"AppleWebKit/537.36 (KHTML, like Gecko) "
        b"Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, parent_popup):
        super().__init__(parent_popup.inner_island)
        self.parent_popup = parent_popup
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_network_reply)
        self.image_cache = OrderedDict()
        self.raw_image_cache = OrderedDict()
        self.failed_urls = {}
        self.pending_requests = set()
        self.active_placeholders = {}
        self.active_replies = {}
        self.code_snippets = []
        self.MAX_CACHE_SIZE = 100
        self.MAX_RAW_CACHE_SIZE = 35
        self.CACHE_TTL = 30

        self.shimmer_phase = 0.0
        self.shimmer_timer = QTimer(self)
        self.shimmer_timer.setInterval(33)
        self.shimmer_timer.timeout.connect(self._tick_shimmer)

        self.scroll_indicator_alpha = 0.0
        self.scroll_fade_timer = QTimer(self)
        self.scroll_fade_timer.setInterval(25)
        self.scroll_fade_timer.timeout.connect(self._tick_scroll_indicator)

        self._revealing_images = {}
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setInterval(16)
        self._reveal_timer.timeout.connect(self._tick_reveal)

        self.verticalScrollBar().valueChanged.connect(self._on_scroll_activity)

        self.cache_dir = "Data/cache"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
        self.meta_cache_file = os.path.join(self.cache_dir, "meta_cache.json")
        self.meta_cache = {}
        if os.path.exists(self.meta_cache_file):
            try:
                with open(self.meta_cache_file, "r", encoding="utf-8") as f:
                    self.meta_cache = json.load(f)
            except Exception:
                pass

        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.handle_link_click)

        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: transparent; border: none; outline: none;")
        self.document().setDocumentMargin(0.0)

        palette = self.palette()
        palette.setColor(QPalette.Highlight, QColor(191, 90, 242, 110))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255, 255))
        self.setPalette(palette)

    def _on_scroll_activity(self):
        self.scroll_indicator_alpha = 1.0
        if not self.scroll_fade_timer.isActive():
            self.scroll_fade_timer.start()
        self.viewport().update()

    def _tick_scroll_indicator(self):
        if self.underMouse():
            target = 0.72
        else:
            target = 0.0
        diff = target - self.scroll_indicator_alpha
        if abs(diff) < 0.03:
            self.scroll_indicator_alpha = target
            if target == 0.0:
                self.scroll_fade_timer.stop()
        else:
            self.scroll_indicator_alpha += diff * 0.14
        self.viewport().update()

    def enterEvent(self, event):
        if self.verticalScrollBar().maximum() > 0:
            self.scroll_indicator_alpha = max(self.scroll_indicator_alpha, 0.72)
            if not self.scroll_fade_timer.isActive():
                self.scroll_fade_timer.start()
            self.viewport().update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.scroll_fade_timer.isActive():
            self.scroll_fade_timer.start()
        super().leaveEvent(event)

    def normalize_document_layout(self):
        doc = self.document()
        if doc is None:
            return
        doc.setDocumentMargin(0.0)

        block = doc.begin()
        while block.isValid():
            if "\ufffc" in block.text():
                fmt = block.blockFormat()
                fmt.setLineHeight(100.0, QTextBlockFormat.ProportionalHeight)
                fmt.setTopMargin(4.0)
                fmt.setBottomMargin(4.0)
                cursor = QTextCursor(block)
                cursor.setBlockFormat(fmt)
            block = block.next()

        first_block = doc.firstBlock()
        if first_block.isValid():
            fmt = first_block.blockFormat()
            if fmt.topMargin() != 0.0:
                fmt.setTopMargin(0.0)
                cursor = QTextCursor(first_block)
                cursor.setBlockFormat(fmt)

        last_block = doc.lastBlock()
        if last_block.isValid():
            fmt = last_block.blockFormat()
            fmt.setBottomMargin(0.0)
            if last_block.blockNumber() > 0 and last_block.text().strip() == "":
                fmt.setTopMargin(0.0)
                fmt.setLineHeight(1.0, QTextBlockFormat.FixedHeight)
                cursor = QTextCursor(last_block)
                cursor.setBlockFormat(fmt)
                char_fmt = cursor.blockCharFormat()
                char_fmt.setFontPointSize(1.0)
                cursor.setBlockCharFormat(char_fmt)
            else:
                cursor = QTextCursor(last_block)
                cursor.setBlockFormat(fmt)

    def _get_dpr(self):
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        return max(1.0, float(dpr))

    def _new_canvas(self, w, h):
        dpr = self._get_dpr()
        img = QImage(
            int(round(w * dpr)),
            int(round(h * dpr)),
            QImage.Format_ARGB32_Premultiplied,
        )
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        return img, dpr

    def _smooth_downscale(self, img, target_w, target_h, mode=Qt.KeepAspectRatioByExpanding):
        tw = int(round(target_w))
        th = int(round(target_h))
        if tw <= 0 or th <= 0:
            return img
        cur = img
        safety = 0
        while (cur.width() > tw * 2 or cur.height() > th * 2) and safety < 8:
            cur = cur.scaled(
                max(tw, cur.width() // 2),
                max(th, cur.height() // 2),
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )
            safety += 1
        return cur.scaled(tw, th, mode, Qt.SmoothTransformation)

    def _store_raw_image(self, key, raw_image):
        if raw_image is None or raw_image.isNull():
            return
        if key in self.raw_image_cache:
            self.raw_image_cache.move_to_end(key)
        self.raw_image_cache[key] = raw_image
        while len(self.raw_image_cache) > self.MAX_RAW_CACHE_SIZE:
            self.raw_image_cache.popitem(last=False)

    def handle_link_click(self, url):
        url_str = url.toString()
        if url_str.startswith("copycode://"):
            try:
                idx = int(url_str[len("copycode://"):])
                if 0 <= idx < len(self.code_snippets):
                    QApplication.clipboard().setText(self.code_snippets[idx])
                    if hasattr(self.parent_popup, "copy_btn"):
                        self.parent_popup.copy_btn.show_copied()
            except Exception:
                pass
            return

        if url_str.startswith("imgpreview:"):
            encoded = url_str[len("imgpreview:"):]
            target_url = _decode_resource_payload(encoded)
            raw_img = (
                self.raw_image_cache.get(target_url)
                or self.raw_image_cache.get("img:" + _encode_resource_payload(target_url))
            )
            if raw_img is not None and not raw_img.isNull() and hasattr(self.parent_popup, "open_image_preview"):
                self.parent_popup.open_image_preview(raw_img, target_url)
                return
            if target_url:
                QDesktopServices.openUrl(QUrl(target_url))
            return
        QDesktopServices.openUrl(url)

    def _register_placeholder(self, url, text, w, h, is_card, animated=True):
        if animated:
            self.active_placeholders[url] = (text, w, h, is_card)
            if not self.shimmer_timer.isActive():
                self.shimmer_timer.start()
        else:
            self.active_placeholders.pop(url, None)
        return self._create_placeholder(text, w=w, h=h, is_card=is_card, phase=self.shimmer_phase if animated else -1.0)

    def _tick_shimmer(self):
        if not self.active_placeholders or self.document() is None:
            self.shimmer_timer.stop()
            return
        self.shimmer_phase = (self.shimmer_phase + 0.042) % 1.0
        doc = self.document()
        for url, (text, w, h, is_card) in list(self.active_placeholders.items()):
            img = self._create_placeholder(text, w=w, h=h, is_card=is_card, phase=self.shimmer_phase)
            doc.addResource(QTextDocument.ImageResource, QUrl(url), img)
        self.viewport().update()

    def clear_Completed_Stream_Placeholders(self):
        for k in ("loading://image", "loading://preview"):
            self.active_placeholders.pop(k, None)
        if not self.active_placeholders and self.shimmer_timer.isActive():
            self.shimmer_timer.stop()

    def _create_placeholder(self, text, w=656, h=308, is_card=False, phase=-1.0):
        img, _ = self._new_canvas(w, h)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, 14.0, 14.0)

        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor(28, 30, 39, 242))
        grad.setColorAt(1.0, QColor(16, 17, 23, 248))
        painter.fillPath(path, grad)

        painter.save()
        painter.setClipPath(path)

        if is_card:
            hero_h = 222.0
            shimmer_rect = QRectF(1.0, 1.0, w - 2.0, hero_h)
            painter.fillRect(shimmer_rect, QColor(255, 255, 255, 7))
            painter.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
            painter.drawLine(QPointF(1.0, hero_h), QPointF(w - 1.0, hero_h))

            bar1 = QPainterPath()
            bar1.addRoundedRect(QRectF(18.0, hero_h + 18.0, w * 0.48, 13.0), 6.5, 6.5)
            painter.fillPath(bar1, QColor(255, 255, 255, 24))

            bar2 = QPainterPath()
            bar2.addRoundedRect(QRectF(18.0, hero_h + 40.0, w * 0.74, 10.0), 5.0, 5.0)
            painter.fillPath(bar2, QColor(255, 255, 255, 14))

            bar3 = QPainterPath()
            bar3.addRoundedRect(QRectF(18.0, hero_h + 62.0, w * 0.24, 9.0), 4.5, 4.5)
            painter.fillPath(bar3, QColor(191, 90, 242, 42))

            text_rect = QRectF(0.0, 0.0, float(w), hero_h)
        else:
            text_rect = QRectF(0.0, 0.0, float(w), float(h))

        if phase >= 0.0:
            sweep_span = w * 0.65
            cx = -sweep_span + (w + sweep_span * 2.0) * phase
            shimmer_grad = QLinearGradient(
                QPointF(cx - sweep_span * 0.5, 0.0),
                QPointF(cx + sweep_span * 0.5, h * 0.35),
            )
            shimmer_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            shimmer_grad.setColorAt(0.45, QColor(196, 138, 249, 18))
            shimmer_grad.setColorAt(0.5, QColor(255, 255, 255, 32))
            shimmer_grad.setColorAt(0.55, QColor(196, 138, 249, 18))
            shimmer_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, shimmer_grad)

        painter.restore()

        painter.setPen(QColor(186, 188, 205, 215))
        font = QFont(getattr(self.parent_popup, "eng_font", "Segoe UI"), 9, QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignCenter, text)

        pen = QPen(QColor(255, 255, 255, 30), 1.1)
        painter.strokePath(path, pen)
        painter.end()
        return img

    def save_meta_cache(self):
        try:
            with open(self.meta_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.meta_cache, f)
        except Exception:
            pass

    def _build_request(self, target_url, accept_images=False):
        req = QNetworkRequest(QUrl(target_url))
        req.setRawHeader(b"User-Agent", self.USER_AGENT)
        if accept_images:
            req.setRawHeader(
                b"Accept",
                b"image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            )
        else:
            req.setRawHeader(
                b"Accept",
                b"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            )
        if hasattr(QNetworkRequest, "FollowRedirectsAttribute"):
            req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        if hasattr(QNetworkRequest, "RedirectPolicyAttribute") and hasattr(
            QNetworkRequest, "NoLessSafeRedirectPolicy"
        ):
            req.setAttribute(
                QNetworkRequest.RedirectPolicyAttribute,
                QNetworkRequest.NoLessSafeRedirectPolicy,
            )
        return req

    def _send_get(self, req, timeout_ms=12000, **props):
        reply = self.network_manager.get(req)
        for k, v in props.items():
            reply.setProperty(k, v)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda r=reply: self._abort_stalled_reply(r))
        timer.start(timeout_ms)
        self.active_replies[reply] = timer
        return reply

    def _abort_stalled_reply(self, reply):
        self.active_replies.pop(reply, None)
        try:
            if reply is not None and reply.isRunning():
                reply.abort()
        except Exception:
            pass

    def _is_transient_error(self, reply):
        try:
            err = reply.error()
            candidates = []
            for name in ("TimeoutError", "TemporaryNetworkFailureError", "ConnectionRefusedError"):
                if hasattr(QNetworkReply, name):
                    candidates.append(getattr(QNetworkReply, name))
            return err in candidates
        except Exception:
            return False

    def _retry_image(self, url, original_url, meta_data, is_preview, retry_count):
        if not url:
            return
        req = self._build_request(url, accept_images=True)
        self._send_get(
            req,
            is_preview_img=is_preview,
            original_url=original_url,
            actual_url=url,
            meta_data=meta_data,
            retry_count=retry_count,
        )

    def _decode_image_bytes(self, raw_bytes):
        if not raw_bytes:
            return QImage()
        img = QImage.fromData(raw_bytes)
        if not img.isNull():
            return img
        try:
            renderer = QSvgRenderer(QByteArray(raw_bytes))
            if not renderer.isValid():
                return QImage()
            size = renderer.defaultSize()
            dw = max(1, size.width())
            dh = max(1, size.height())
            aspect = dw / float(dh)
            if self.IMG_W / float(self.IMG_H) > aspect:
                target_h = self.IMG_H
                target_w = max(self.IMG_W, int(target_h * aspect))
            else:
                target_w = self.IMG_W
                target_h = max(self.IMG_H, int(target_w / aspect))
            svg_img = QImage(target_w, target_h, QImage.Format_ARGB32_Premultiplied)
            svg_img.fill(Qt.transparent)
            p = QPainter(svg_img)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            renderer.render(p, QRectF(0, 0, target_w, target_h))
            p.end()
            return svg_img
        except Exception:
            return QImage()

    def _load_local_image(self, local_path):
        img = QImage(local_path)
        if not img.isNull():
            return img
        if os.path.exists(local_path):
            try:
                with open(local_path, "rb") as f:
                    return self._decode_image_bytes(f.read())
            except Exception:
                pass
        return QImage()

    def _create_reveal_frame(self, img, progress):
        dpr = img.devicePixelRatio()
        if dpr <= 0:
            dpr = 1.0
        logical_w = img.width() / dpr
        logical_h = img.height() / dpr

        p = max(0.0, min(1.0, progress))
        eased = p * p * (3.0 - 2.0 * p)

        canvas = QImage(img.width(), img.height(), QImage.Format_ARGB32_Premultiplied)
        canvas.setDevicePixelRatio(dpr)
        canvas.fill(Qt.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        scale = 0.92 + 0.08 * eased
        slide_y = (1.0 - eased) * 8.0
        opacity = 0.55 + 0.45 * eased

        ccx = logical_w / 2.0
        ccy = logical_h / 2.0
        painter.translate(ccx, ccy + slide_y)
        painter.scale(scale, scale)
        painter.translate(-ccx, -ccy)

        painter.setOpacity(opacity)
        painter.drawImage(0, 0, img)

        painter.end()
        return canvas

    def _tick_reveal(self):
        if not self._revealing_images:
            self._reveal_timer.stop()
            return

        doc = self.document()
        if doc is None:
            self._revealing_images.clear()
            self._reveal_timer.stop()
            return

        for url in list(self._revealing_images.keys()):
            data = self._revealing_images[url]
            data["progress"] = min(1.0, data["progress"] + 0.05)
            p = data["progress"]
            final_img = data["final"]

            if p >= 1.0:
                if len(self.image_cache) >= self.MAX_CACHE_SIZE:
                    self.image_cache.popitem(last=False)
                self.image_cache[url] = final_img
                doc.addResource(QTextDocument.ImageResource, QUrl(url), final_img)
                del self._revealing_images[url]
            else:
                revealed = self._create_reveal_frame(final_img, p)
                doc.addResource(QTextDocument.ImageResource, QUrl(url), revealed)

        doc.markContentsDirty(0, max(1, doc.characterCount()))
        self.viewport().update()

        if not self._revealing_images:
            self._reveal_timer.stop()
            self._trigger_debounced_reflow()

    def loadResource(self, type, name):
        if type == QTextDocument.ImageResource:
            url = name.toString()
            current_time = time.time()

            if url == "loading://image":
                return self._register_placeholder(url, "Loading Image...", self.IMG_W, self.IMG_H, False, True)
            if url == "loading://preview":
                return self._register_placeholder(url, "Loading Preview...", self.CARD_W, self.CARD_H, True, True)

            if url in self._revealing_images:
                data = self._revealing_images[url]
                return self._create_reveal_frame(data["final"], data["progress"])

            if url in self.image_cache:
                self.image_cache.move_to_end(url)
                return self.image_cache[url]

            is_preview_scheme = url.startswith("preview:")
            is_img_scheme = url.startswith("img:")

            if url in self.failed_urls:
                if current_time - self.failed_urls[url] < self.CACHE_TTL:
                    if is_preview_scheme:
                        actual_url = _decode_resource_payload(url[8:])
                        meta = {
                            "title": actual_url,
                            "description": "Click to open link in browser",
                            "domain": urllib.parse.urlparse(actual_url).netloc or "Web Link",
                        }
                        return self._draw_card(None, url, meta)
                    return self._register_placeholder(url, "Image Unavailable", self.IMG_W, self.IMG_H, False, False)
                else:
                    del self.failed_urls[url]

            if url in self.pending_requests:
                if is_preview_scheme:
                    return self._register_placeholder(url, "Loading Link Preview...", self.CARD_W, self.CARD_H, True, True)
                return self._register_placeholder(url, "Loading Media...", self.IMG_W, self.IMG_H, False, True)

            if is_preview_scheme:
                actual_url = _decode_resource_payload(url[8:])
                if not actual_url:
                    self.failed_urls[url] = current_time
                    return self._register_placeholder(url, "Invalid Preview", self.CARD_W, self.CARD_H, True, False)

                if actual_url in self.meta_cache:
                    meta = self.meta_cache[actual_url]
                    img_url = meta.get("img_url")
                    if img_url:
                        self.pending_requests.add(url)
                        self._request_image(img_url, url, meta)
                        return self._register_placeholder(url, "Loading Link Preview...", self.CARD_W, self.CARD_H, True, True)
                    else:
                        styled = self._draw_card(None, url, meta)
                        return self._cache_and_update(url, styled, animate=False)

                self.pending_requests.add(url)
                api_url = (
                    f"https://api.microlink.io?url={urllib.parse.quote(actual_url, safe='')}"
                    f"&screenshot=true&meta=true&colorScheme=dark"
                )
                req = self._build_request(api_url, accept_images=False)
                self._send_get(
                    req,
                    is_microlink=True,
                    original_url=url,
                    actual_url=actual_url,
                )
                return self._register_placeholder(url, "Loading Link Preview...", self.CARD_W, self.CARD_H, True, True)

            if is_img_scheme:
                actual_media_url = _decode_resource_payload(url[4:])
                if not actual_media_url:
                    self.failed_urls[url] = current_time
                    return self._register_placeholder(url, "Invalid Image", self.IMG_W, self.IMG_H, False, False)

                if actual_media_url.startswith("file://"):
                    local_path = QUrl(actual_media_url).toLocalFile()
                    raw_image = self._load_local_image(local_path)
                    if not raw_image.isNull():
                        self._store_raw_image(actual_media_url, raw_image)
                        self._store_raw_image(url, raw_image)
                        styled_img = self._style_simple_image(raw_image, actual_media_url)
                        return self._cache_and_update(url, styled_img, animate=True)
                    else:
                        self.failed_urls[url] = current_time
                        return self._register_placeholder(url, "Local Image Not Found", self.IMG_W, self.IMG_H, False, False)

                if actual_media_url.startswith(("http://", "https://")):
                    self.pending_requests.add(url)
                    req = self._build_request(actual_media_url, accept_images=True)
                    self._send_get(
                        req,
                        is_direct_image=True,
                        original_url=url,
                        actual_url=actual_media_url,
                    )
                    return self._register_placeholder(url, "Loading Media...", self.IMG_W, self.IMG_H, False, True)

                self.failed_urls[url] = current_time
                return self._register_placeholder(url, "Image Unavailable", self.IMG_W, self.IMG_H, False, False)

        return super().loadResource(type, name)

    def _request_image(self, img_url, original_url, meta_data=None):
        req = self._build_request(img_url, accept_images=True)
        self._send_get(
            req,
            is_preview_img=True,
            original_url=original_url,
            actual_url=img_url,
            meta_data=meta_data,
        )

    def _cache_and_update(self, url, img, animate=True):
        self.active_placeholders.pop(url, None)
        self.pending_requests.discard(url)
        if not self.active_placeholders and self.shimmer_timer.isActive():
            self.shimmer_timer.stop()

        if url in self.image_cache:
            self.image_cache.move_to_end(url)
            doc = self.document()
            if doc is not None:
                doc.addResource(QTextDocument.ImageResource, QUrl(url), img)
                self.normalize_document_layout()
                doc.markContentsDirty(0, max(1, doc.characterCount()))
            self.viewport().update()
            self._trigger_debounced_reflow()
            return img

        if not animate:
            if len(self.image_cache) >= self.MAX_CACHE_SIZE:
                self.image_cache.popitem(last=False)
            self.image_cache[url] = img
            doc = self.document()
            if doc is not None:
                doc.addResource(QTextDocument.ImageResource, QUrl(url), img)
                self.normalize_document_layout()
                doc.markContentsDirty(0, max(1, doc.characterCount()))
            self.viewport().update()
            self._trigger_debounced_reflow()
            return img

        self._revealing_images[url] = {"final": img, "progress": 0.05}
        if not self._reveal_timer.isActive():
            self._reveal_timer.start()

        initial = self._create_reveal_frame(img, 0.05)
        doc = self.document()
        if doc is not None:
            doc.addResource(QTextDocument.ImageResource, QUrl(url), initial)
            self.normalize_document_layout()
            doc.markContentsDirty(0, max(1, doc.characterCount()))
        self.viewport().update()
        self._trigger_debounced_reflow()
        return initial

    def _create_smooth_blurred_backdrop(self, raw_image, target_w, target_h):
        s1 = raw_image.scaled(128, 72, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        s2 = s1.scaled(36, 20, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        s3 = s2.scaled(96, 54, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        s4 = s3.scaled(28, 16, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return s4.scaled(target_w, target_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def _style_simple_image(self, raw_image, url):
        w, h = self.IMG_W, self.IMG_H
        styled_img, dpr = self._new_canvas(w, h)

        painter = QPainter(styled_img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, 14.0, 14.0)
        painter.fillPath(path, QColor(14, 15, 20))
        painter.setClipPath(path)

        orig_w = max(1, raw_image.width())
        orig_h = max(1, raw_image.height())
        img_ratio = orig_w / float(orig_h)
        is_yt = "img.youtube.com" in url

        if is_yt or (1.52 <= img_ratio <= 2.35 and orig_w >= 320):
            scaled_fill = self._smooth_downscale(
                raw_image,
                w * dpr,
                h * dpr,
                Qt.KeepAspectRatioByExpanding,
            )
            sw = scaled_fill.width() / dpr
            sh = scaled_fill.height() / dpr
            dx = (w - sw) / 2.0
            dy = (h - sh) / 2.0
            painter.drawImage(QRectF(dx, dy, sw, sh), scaled_fill)
        else:
            blurred_bg = self._create_smooth_blurred_backdrop(
                raw_image,
                int(round(w * dpr)),
                int(round(h * dpr)),
            )
            painter.drawImage(QRectF(0.0, 0.0, float(w), float(h)), blurred_bg)
            painter.fillRect(QRectF(0.0, 0.0, float(w), float(h)), QColor(11, 12, 17, 172))

            avail_w = w - 28.0
            avail_h = h - 24.0
            scaled_fit = self._smooth_downscale(
                raw_image,
                avail_w * dpr,
                avail_h * dpr,
                Qt.KeepAspectRatio,
            )
            fw = scaled_fit.width() / dpr
            fh = scaled_fit.height() / dpr
            fx = (w - fw) / 2.0
            fy = (h - fh) / 2.0

            shadow_rect = QRectF(fx - 2.0, fy + 2.0, fw + 4.0, fh + 4.0)
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(shadow_rect, 10.0, 10.0)
            painter.fillPath(shadow_path, QColor(0, 0, 0, 95))

            inner_rect = QRectF(fx, fy, fw, fh)
            inner_path = QPainterPath()
            inner_path.addRoundedRect(inner_rect, 9.0, 9.0)
            painter.save()
            painter.setClipPath(inner_path, Qt.IntersectClip)
            painter.drawImage(inner_rect, scaled_fit)
            painter.restore()
            painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
            painter.drawRoundedRect(inner_rect, 9.0, 9.0)

        if is_yt:
            footer_grad = QLinearGradient(0.0, h - 56.0, 0.0, float(h))
            footer_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            footer_grad.setColorAt(1.0, QColor(8, 9, 13, 195))
            painter.fillRect(QRectF(0.0, h - 56.0, float(w), 56.0), footer_grad)

            pill_w, pill_h = 62.0, 42.0
            pill_x, pill_y = (w - pill_w) / 2.0, (h - pill_h) / 2.0
            path_pill = QPainterPath()
            path_pill.addRoundedRect(pill_x, pill_y, pill_w, pill_h, 12.0, 12.0)
            painter.fillPath(path_pill, QColor(255, 18, 38, 238))
            painter.setPen(QPen(QColor(255, 255, 255, 55), 1.0))
            painter.drawPath(path_pill)

            triangle = QPainterPath()
            tx, ty = pill_x + 25.0, pill_y + 12.5
            triangle.moveTo(tx, ty)
            triangle.lineTo(tx + 15.5, ty + 8.5)
            triangle.lineTo(tx, ty + 17.0)
            triangle.closeSubpath()
            painter.fillPath(triangle, QColor(255, 255, 255))
        else:
            footer_grad = QLinearGradient(0.0, h - 52.0, 0.0, float(h))
            footer_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            footer_grad.setColorAt(1.0, QColor(8, 9, 13, 195))
            painter.fillRect(QRectF(0.0, h - 52.0, float(w), 52.0), footer_grad)

            eng_font = getattr(self.parent_popup, "eng_font", "Segoe UI")
            domain = urllib.parse.urlparse(url).netloc if url.startswith("http") else "Local Media"
            info_label = f"{domain}  •  {orig_w}×{orig_h}" if domain else f"{orig_w}×{orig_h}"

            badge_font = QFont(eng_font, 8, QFont.DemiBold)
            painter.setFont(badge_font)
            fm_info = QFontMetrics(badge_font)
            info_w = min(w - 130.0, float(fm_info.horizontalAdvance(info_label) + 18))

            info_rect = QRectF(12.0, h - 32.0, info_w, 22.0)
            info_path = QPainterPath()
            info_path.addRoundedRect(info_rect, 7.0, 7.0)
            painter.fillPath(info_path, QColor(15, 16, 22, 175))
            painter.setPen(QPen(QColor(255, 255, 255, 32), 0.8))
            painter.drawPath(info_path)

            painter.setPen(QColor(235, 235, 245, 230))
            painter.drawText(info_rect.adjusted(9.0, 0.0, -6.0, 0.0), Qt.AlignLeft | Qt.AlignVCenter, info_label)

            zoom_rect = QRectF(w - 86.0, h - 32.0, 74.0, 22.0)
            zoom_path = QPainterPath()
            zoom_path.addRoundedRect(zoom_rect, 7.0, 7.0)
            painter.fillPath(zoom_path, QColor(255, 255, 255, 32))
            painter.setPen(QPen(QColor(255, 255, 255, 55), 0.9))
            painter.drawPath(zoom_path)

            painter.setPen(QColor(255, 255, 255, 242))
            painter.drawText(zoom_rect, Qt.AlignCenter, "Expand ⤢")

        painter.setClipping(False)
        pen = QPen(QColor(255, 255, 255, 38), 1.15)
        painter.strokePath(path, pen)
        painter.end()
        return styled_img

    def _draw_card(self, raw_image, url, meta):
        w, h = self.CARD_W, self.CARD_H
        img_h = 222
        meta = meta or {}
        styled_img, dpr = self._new_canvas(w, h)

        painter = QPainter(styled_img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, 14.0, 14.0)
        painter.fillPath(path, QColor(20, 21, 28, 250))
        painter.setClipPath(path)

        if raw_image is None or raw_image.isNull():
            hero_grad = QLinearGradient(0.0, 0.0, float(w), float(img_h))
            hero_grad.setColorAt(0.0, QColor(36, 32, 52))
            hero_grad.setColorAt(1.0, QColor(21, 22, 31))
            painter.fillRect(QRectF(0.0, 0.0, float(w), float(img_h)), hero_grad)

            domain_label = str(meta.get("domain") or "WEB").upper()
            eng_font = getattr(self.parent_popup, "eng_font", "Segoe UI")
            watermark_font = QFont(eng_font, 15, QFont.Bold)
            painter.setFont(watermark_font)
            painter.setPen(QColor(196, 138, 249, 90))
            painter.drawText(QRectF(0.0, 0.0, float(w), float(img_h)), Qt.AlignCenter, domain_label)
        else:
            scaled_hero = self._smooth_downscale(
                raw_image,
                w * dpr,
                img_h * dpr,
                Qt.KeepAspectRatioByExpanding,
            )
            sw = scaled_hero.width() / dpr
            sh = scaled_hero.height() / dpr
            img_x = (w - sw) / 2.0
            img_y = (img_h - sh) / 2.0
            painter.save()
            painter.setClipRect(QRectF(0.0, 0.0, float(w), float(img_h)), Qt.IntersectClip)
            painter.drawImage(QRectF(img_x, img_y, sw, sh), scaled_hero)
            hero_fade = QLinearGradient(0.0, img_h - 48.0, 0.0, float(img_h))
            hero_fade.setColorAt(0.0, QColor(20, 21, 28, 0))
            hero_fade.setColorAt(1.0, QColor(20, 21, 28, 165))
            painter.fillRect(QRectF(0.0, img_h - 48.0, float(w), 48.0), hero_fade)
            painter.restore()

        painter.setClipping(False)

        title = html_lib.unescape(str(meta.get("title") or "Web Link")).strip()
        desc = html_lib.unescape(str(meta.get("description") or "")).strip()
        domain = html_lib.unescape(str(meta.get("domain") or "")).strip()

        eng_font = getattr(self.parent_popup, "eng_font", "Segoe UI")

        painter.setPen(QColor(255, 255, 255, 248))
        title_font = QFont(eng_font, 10, QFont.Bold)
        painter.setFont(title_font)
        fm_title = QFontMetrics(title_font)
        elided_title = fm_title.elidedText(title, Qt.ElideRight, w - 34)
        painter.drawText(17, img_h + 26, elided_title)

        painter.setPen(QColor(175, 177, 194, 225))
        desc_font = QFont(eng_font, 9, QFont.Normal)
        painter.setFont(desc_font)
        fm_desc = QFontMetrics(desc_font)
        elided_desc = fm_desc.elidedText(desc, Qt.ElideRight, w - 34)
        painter.drawText(17, img_h + 50, elided_desc)

        if domain:
            painter.setPen(QColor(196, 138, 249, 235))
            dom_font = QFont(eng_font, 8, QFont.DemiBold)
            painter.setFont(dom_font)
            painter.drawText(17, img_h + 74, f"{domain} ↗")

        pen = QPen(QColor(255, 255, 255, 36), 1.15)
        painter.strokePath(path, pen)

        line_pen = QPen(QColor(255, 255, 255, 20), 1.0)
        painter.setPen(line_pen)
        painter.drawLine(QPointF(1.5, float(img_h)), QPointF(float(w - 1.5), float(img_h)))

        painter.end()
        return styled_img

    def _draw_thinking_indicator(self, painter):
        phase = getattr(self.parent_popup, "glow_phase", 0.0)
        vp = self.viewport()
        cx = vp.width() / 2.0
        cy = vp.height() / 2.0

        for i in range(3):
            offset = phase * 1.6 + i * 0.7
            alpha_f = (math.sin(offset) + 1.0) * 0.5
            alpha = int(55 + 165 * alpha_f)
            dot_x = cx - 26.0 + i * 26.0
            radius = 4.2 + alpha_f * 1.8
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(191, 90, 242, alpha))
            painter.drawEllipse(QPointF(dot_x, cy), radius, radius)

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.parent_popup is not None:
            status = getattr(self.parent_popup, "status", "")
            if status == "typing" and not self.toPlainText().strip():
                painter = QPainter(self.viewport())
                painter.setRenderHint(QPainter.Antialiasing, True)
                self._draw_thinking_indicator(painter)
                painter.end()

        scrollbar = self.verticalScrollBar()
        max_v = scrollbar.maximum()
        if max_v <= 0:
            return

        cur_v = scrollbar.value()
        vp = self.viewport()
        vw = float(vp.width())
        vh = float(vp.height())

        painter = QPainter(vp)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if cur_v > 2:
            top_grad = QLinearGradient(0.0, 0.0, 0.0, 18.0)
            top_grad.setColorAt(0.0, QColor(18, 19, 25, 210))
            top_grad.setColorAt(1.0, QColor(18, 19, 25, 0))
            painter.fillRect(QRectF(0.0, 0.0, vw, 18.0), top_grad)

        if cur_v < max_v - 2:
            bot_grad = QLinearGradient(0.0, vh - 22.0, 0.0, vh)
            bot_grad.setColorAt(0.0, QColor(11, 12, 16, 0))
            bot_grad.setColorAt(1.0, QColor(11, 12, 16, 220))
            painter.fillRect(QRectF(0.0, vh - 22.0, vw, 22.0), bot_grad)

        if self.scroll_indicator_alpha > 0.01:
            page_step = max(1.0, float(scrollbar.pageStep()))
            total_doc_h = max(1.0, float(max_v + page_step))
            track_margin = 4.0
            track_h = max(24.0, vh - track_margin * 2.0)
            thumb_h = max(28.0, min(track_h, (page_step / total_doc_h) * track_h))
            scroll_ratio = float(cur_v) / float(max_v)
            thumb_y = track_margin + scroll_ratio * (track_h - thumb_h)

            thumb_rect = QRectF(vw - 4.5, thumb_y, 3.2, thumb_h)
            thumb_path = QPainterPath()
            thumb_path.addRoundedRect(thumb_rect, 1.6, 1.6)
            alpha = int(145 * self.scroll_indicator_alpha)
            painter.fillPath(thumb_path, QColor(215, 218, 235, alpha))

        painter.end()

    def _trigger_debounced_reflow(self):
        QTimer.singleShot(10, self.parent_popup.update_layout_height)

    def on_network_reply(self, reply):
        timer = self.active_replies.pop(reply, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

        url = reply.request().url().toString()
        is_microlink = bool(reply.property("is_microlink"))
        is_fallback = bool(reply.property("is_fallback"))
        is_preview_img = bool(reply.property("is_preview_img"))
        original_url = str(reply.property("original_url") or "")
        actual_url = str(reply.property("actual_url") or "")
        meta_data = reply.property("meta_data")
        current_time = time.time()

        target_cleanup_url = original_url if original_url else url

        if self.document() is None:
            self.pending_requests.discard(target_cleanup_url)
            self.active_placeholders.pop(target_cleanup_url, None)
            reply.deleteLater()
            return

        content_length = reply.header(QNetworkRequest.ContentLengthHeader)
        if content_length and int(content_length) > 12 * 1024 * 1024:
            self.pending_requests.discard(target_cleanup_url)
            self.failed_urls[target_cleanup_url] = current_time
            is_card = target_cleanup_url.startswith("preview:")
            ph = self._create_placeholder(
                "Media File Too Large",
                w=self.CARD_W if is_card else self.IMG_W,
                h=self.CARD_H if is_card else self.IMG_H,
                is_card=is_card,
                phase=-1.0,
            )
            self._cache_and_update(target_cleanup_url, ph, animate=False)
            reply.deleteLater()
            return

        if reply.error() != QNetworkReply.NoError:
            retry_count = int(reply.property("retry_count") or 0)
            if (
                not is_microlink
                and not is_fallback
                and retry_count < 2
                and self._is_transient_error(reply)
                and (actual_url or url)
            ):
                delay = 500 if retry_count == 0 else 1500
                retry_url = actual_url or url
                QTimer.singleShot(
                    delay,
                    lambda u=retry_url, o=original_url, m=meta_data, p=is_preview_img, r=retry_count + 1:
                        self._retry_image(u, o, m, p, r),
                )
                reply.deleteLater()
                return

            if is_microlink and actual_url:
                req = self._build_request(actual_url, accept_images=False)
                self._send_get(
                    req,
                    is_fallback=True,
                    original_url=original_url,
                    actual_url=actual_url,
                )
                reply.deleteLater()
                return
            elif is_fallback:
                self.pending_requests.discard(target_cleanup_url)
                self.failed_urls[target_cleanup_url] = current_time
                meta = {
                    "title": actual_url,
                    "description": "Click to open link in browser",
                    "domain": urllib.parse.urlparse(actual_url).netloc or "Web Link",
                }
                styled = self._draw_card(None, original_url, meta)
                self._cache_and_update(original_url, styled, animate=False)
                reply.deleteLater()
                return
            elif "maxresdefault.jpg" in url:
                fallback_url = original_url if original_url else url
                req = self._build_request(url.replace("maxresdefault.jpg", "hqdefault.jpg"), accept_images=True)
                self._send_get(
                    req,
                    is_direct_image=True,
                    original_url=fallback_url,
                    actual_url=actual_url or fallback_url,
                )
                reply.deleteLater()
                return
            elif is_preview_img and meta_data:
                self.pending_requests.discard(target_cleanup_url)
                styled = self._draw_card(None, target_cleanup_url, meta_data)
                self._cache_and_update(target_cleanup_url, styled, animate=False)
                reply.deleteLater()
                return
            else:
                self.pending_requests.discard(target_cleanup_url)
                self.failed_urls[target_cleanup_url] = current_time
                is_card = target_cleanup_url.startswith("preview:")
                ph = self._create_placeholder(
                    "Preview Unavailable",
                    w=self.CARD_W if is_card else self.IMG_W,
                    h=self.CARD_H if is_card else self.IMG_H,
                    is_card=is_card,
                    phase=-1.0,
                )
                self._cache_and_update(target_cleanup_url, ph, animate=False)
                reply.deleteLater()
                return

        if is_microlink:
            try:
                raw_json = reply.readAll().data().decode("utf-8", errors="ignore")
                data = json.loads(raw_json)
                if data.get("status") != "success":
                    raise ValueError("Microlink non-success")
                payload = data.get("data") or {}

                screenshot_obj = payload.get("screenshot")
                screenshot_url = screenshot_obj.get("url") if isinstance(screenshot_obj, dict) else None

                img_obj = payload.get("image")
                og_img_url = img_obj.get("url") if isinstance(img_obj, dict) else None

                logo_obj = payload.get("logo")
                logo_url = logo_obj.get("url") if isinstance(logo_obj, dict) else None

                best_img_url = screenshot_url or og_img_url or logo_url

                title = payload.get("title")
                desc = payload.get("description")
                domain = payload.get("publisher") or urllib.parse.urlparse(actual_url).netloc

                meta = {
                    "title": title or actual_url,
                    "description": desc or "",
                    "domain": domain,
                    "img_url": best_img_url,
                }
                self.meta_cache[actual_url] = meta
                self.save_meta_cache()

                if best_img_url:
                    self._request_image(best_img_url, original_url, meta)
                else:
                    self.pending_requests.discard(original_url)
                    styled = self._draw_card(None, original_url, meta)
                    self._cache_and_update(original_url, styled, animate=False)
            except Exception:
                self.pending_requests.discard(original_url)
                self.failed_urls[original_url] = current_time
                req = self._build_request(actual_url, accept_images=False)
                self._send_get(
                    req,
                    is_fallback=True,
                    original_url=original_url,
                    actual_url=actual_url,
                )
            reply.deleteLater()
            return

        if is_fallback:
            raw_bytes = reply.readAll().data()
            content_type = str(reply.header(QNetworkRequest.ContentTypeHeader) or "").lower()
            domain = urllib.parse.urlparse(actual_url).netloc

            if content_type.startswith("image/"):
                raw_img = self._decode_image_bytes(raw_bytes)
                self.pending_requests.discard(original_url)
                if not raw_img.isNull():
                    self._store_raw_image(actual_url, raw_img)
                    meta = {
                        "title": os.path.basename(urllib.parse.urlparse(actual_url).path) or domain or "Image",
                        "description": f"{raw_img.width()}×{raw_img.height()} Image",
                        "domain": domain,
                        "img_url": actual_url,
                    }
                    styled = self._draw_card(raw_img, original_url, meta)
                    self._cache_and_update(original_url, styled, animate=False)
                    reply.deleteLater()
                    return

            html = raw_bytes.decode("utf-8", errors="ignore")
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            desc_match = re.search(
                r'<meta\s+(?:property|name)=["\'](?:og:description|description)["\']\s+content=["\'](.*?)["\']',
                html,
                re.IGNORECASE,
            )
            img_match = re.search(
                r'<meta\s+(?:property|name)=["\'](?:og:image|twitter:image)["\']\s+content=["\'](.*?)["\']',
                html,
                re.IGNORECASE,
            )

            title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else actual_url
            desc = desc_match.group(1).strip() if desc_match else ""
            img_url = img_match.group(1).strip() if img_match else None

            meta = {"title": title, "description": desc, "domain": domain, "img_url": img_url}
            self.meta_cache[actual_url] = meta
            self.save_meta_cache()

            if img_url:
                img_url = urllib.parse.urljoin(actual_url, img_url)
                self._request_image(img_url, original_url, meta)
            else:
                self.pending_requests.discard(original_url)
                styled = self._draw_card(None, original_url, meta)
                self._cache_and_update(original_url, styled, animate=False)
            reply.deleteLater()
            return

        raw_bytes = reply.readAll().data()
        raw_image = self._decode_image_bytes(raw_bytes)
        target_url = original_url or url

        self.pending_requests.discard(target_cleanup_url)

        if raw_image.isNull():
            if is_preview_img and meta_data:
                styled = self._draw_card(None, target_url, meta_data)
                self._cache_and_update(target_url, styled, animate=False)
            else:
                self.failed_urls[target_url] = current_time
                ph = self._create_placeholder(
                    "Invalid Image Data",
                    w=self.IMG_W,
                    h=self.IMG_H,
                    is_card=False,
                    phase=-1.0,
                )
                self._cache_and_update(target_url, ph, animate=False)
            reply.deleteLater()
            return

        if is_preview_img and meta_data:
            styled_img = self._draw_card(raw_image, target_url, meta_data)
            self._cache_and_update(target_url, styled_img, animate=False)
        else:
            media_key = actual_url or ""
            self._store_raw_image(media_key, raw_image)
            self._store_raw_image(target_url, raw_image)
            styled_img = self._style_simple_image(raw_image, media_key)
            self._cache_and_update(target_url, styled_img, animate=True)

        reply.deleteLater()