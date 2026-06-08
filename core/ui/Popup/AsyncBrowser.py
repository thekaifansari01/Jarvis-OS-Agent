import json
import urllib.parse
from collections import OrderedDict
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QTextBrowser, QFrame, QSizePolicy
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTextDocument, QPalette, QDesktopServices

class AsyncTextBrowser(QTextBrowser):
    def __init__(self, parent_popup):
        super().__init__(parent_popup.inner_island)
        self.parent_popup = parent_popup  
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_image_downloaded)
        self.image_cache = OrderedDict()
        self.failed_urls = set()
        
        self.pending_requests = set()
        
        self.MAX_CACHE_SIZE = 50
        
        self.setOpenLinks(False) 
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.handle_link_click)
        
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: transparent; border: none; outline: none;")

        palette = self.palette()
        palette.setColor(QPalette.Highlight, QColor(191, 90, 242, 100))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255, 255))
        self.setPalette(palette)

    def handle_link_click(self, url):
        QDesktopServices.openUrl(url)

    def _create_placeholder(self, text):
        img = QImage(380, 214, QImage.Format_ARGB32)
        img.fill(QColor(40, 40, 45, 150))
        painter = QPainter(img)
        painter.setPen(QColor(160, 160, 165))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(img.rect(), Qt.AlignCenter, text)
        painter.end()
        return img

    def loadResource(self, type, name):
        if type == QTextDocument.ImageResource:
            url = name.toString()
            
            if url in self.failed_urls: 
                return self._create_placeholder("Preview Unavailable")

            if url in self.image_cache:
                self.image_cache.move_to_end(url)
                return self.image_cache[url]
            
            if url in self.pending_requests:
                return self._create_placeholder("Loading...")
            
            self.pending_requests.add(url)
            
            if url.startswith('preview://'):
                actual_url = url[10:]
                api_url = f"https://api.microlink.io?url={urllib.parse.quote(actual_url)}"
                req = QNetworkRequest(QUrl(api_url))
                req.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                reply = self.network_manager.get(req)
                
                reply.setProperty("is_meta", True)
                reply.setProperty("original_url", url) 
                return self._create_placeholder("Fetching Preview...")
                
            elif url.startswith('http'):
                req = QNetworkRequest(QUrl(url))
                req.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                self.network_manager.get(req)
                return self._create_placeholder("Loading Image...")
                
            elif url.startswith('file://'):
                local_path = QUrl(url).toLocalFile()
                raw_image = QImage(local_path)
                
                self.pending_requests.remove(url)
                
                if not raw_image.isNull():
                    styled_img = self._style_image(raw_image, url)
                    if len(self.image_cache) >= self.MAX_CACHE_SIZE: self.image_cache.popitem(last=False)
                    self.image_cache[url] = styled_img
                    return styled_img
                else:
                    self.failed_urls.add(url)
                    return self._create_placeholder("File Not Found")
                
        return super().loadResource(type, name)

    def _style_image(self, raw_image, url):
        if raw_image.width() > 380: raw_image = raw_image.scaledToWidth(380, Qt.SmoothTransformation)
        w, h = raw_image.width(), raw_image.height()
        
        styled_img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        styled_img.fill(Qt.transparent)
        painter = QPainter(styled_img)
        painter.setRenderHint(QPainter.Antialiasing); painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        path = QPainterPath(); path.addRoundedRect(1.5, 1.5, w - 3, h - 3, 10, 10) 
        painter.fillPath(path, QColor(240, 240, 245))
        painter.setClipPath(path)
        painter.drawImage(0, 0, raw_image)
        painter.setClipping(False)

        if "img.youtube.com" in url:
            pill_w, pill_h = 50, 36 
            pill_x, pill_y = (w - pill_w) / 2, (h - pill_h) / 2
            path_pill = QPainterPath(); path_pill.addRoundedRect(pill_x, pill_y, pill_w, pill_h, 8, 8)
            painter.fillPath(path_pill, QColor(255, 0, 0, 220))
            triangle = QPainterPath(); tx, ty = pill_x + 20, pill_y + 10
            triangle.moveTo(tx, ty); triangle.lineTo(tx + 14, ty + 8); triangle.lineTo(tx, ty + 16); triangle.closeSubpath()
            painter.fillPath(triangle, QColor(255, 255, 255))

        pen = QPen(QColor(255, 255, 255)); pen.setWidthF(1.5); painter.strokePath(path, pen)
        painter.end()
        return styled_img

    def on_image_downloaded(self, reply):
        if not self.isVisible() or self.document() is None:
            reply.deleteLater()
            return
            
        url = reply.request().url().toString()
        is_meta = reply.property("is_meta")
        original_url = reply.property("original_url")
        
        target_cleanup_url = original_url if original_url else url
        if target_cleanup_url in self.pending_requests:
            self.pending_requests.remove(target_cleanup_url)

        if reply.error() != QNetworkReply.NoError:
            if is_meta:
                self.failed_urls.add(original_url)
                self.document().addResource(QTextDocument.ImageResource, QUrl(original_url), self._create_placeholder("Preview Failed"))
                self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
            elif "maxresdefault.jpg" in url:
                fallback_original_url = original_url if original_url else url
                self.pending_requests.add(fallback_original_url)
                
                req = QNetworkRequest(QUrl(url.replace("maxresdefault.jpg", "hqdefault.jpg")))
                req.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                fallback = self.network_manager.get(req)
                
                fallback.setProperty("original_url", fallback_original_url)
            else: 
                target = original_url if reply.property("is_preview_img") else url
                self.failed_urls.add(target) 
                self.document().addResource(QTextDocument.ImageResource, QUrl(target), self._create_placeholder("Image Load Failed"))
                self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
            reply.deleteLater()
            return

        if is_meta:
            try:
                data = json.loads(reply.readAll().data().decode('utf-8'))
                img_url = data.get('data', {}).get('image', {}).get('url')
                if img_url:
                    self.pending_requests.add(original_url)
                    
                    req = QNetworkRequest(QUrl(img_url))
                    req.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                    img_reply = self.network_manager.get(req)
                    img_reply.setProperty("is_preview_img", True)
                    img_reply.setProperty("original_url", original_url)
                else:
                    self.failed_urls.add(original_url)
                    self.document().addResource(QTextDocument.ImageResource, QUrl(original_url), self._create_placeholder("No Preview Found"))
                    self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
            except Exception:
                self.failed_urls.add(original_url)
                self.document().addResource(QTextDocument.ImageResource, QUrl(original_url), self._create_placeholder("API Error"))
                self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
            reply.deleteLater()
            return

        raw_image = QImage.fromData(reply.readAll())
        target_url = reply.property("original_url") or url
        
        if raw_image.isNull():
            self.failed_urls.add(target_url)
            self.document().addResource(QTextDocument.ImageResource, QUrl(target_url), self._create_placeholder("Invalid Image Data"))
            self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
            reply.deleteLater()
            return

        styled_img = self._style_image(raw_image, target_url)
        if len(self.image_cache) >= self.MAX_CACHE_SIZE: self.image_cache.popitem(last=False) 
        self.image_cache[target_url] = styled_img
        
        self.document().addResource(QTextDocument.ImageResource, QUrl(target_url), styled_img)
        self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth()) 
        self.parent_popup.update_layout_height()
        
        reply.deleteLater()