import re
import base64
import urllib.parse
import pygments.util
from PyQt5.QtCore import QThread, pyqtSignal
from markdown2 import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter


def _encode_resource_payload(url):
    try:
        raw = str(url or "").encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    except Exception:
        return ""


class ParserWorker(QThread):
    finished_signal = pyqtSignal(list, str)

    CARD_W = 656
    CARD_H = 316
    IMG_W = 656
    IMG_H = 308

    IMAGE_EXT_RE = re.compile(
        r"\.(?:png|jpg|jpeg|gif|webp|bmp|svg|avif|ico|tiff)(?:[?#][^\s<>\"')]*)?$",
        re.IGNORECASE,
    )
    KNOWN_IMG_HOST_RE = re.compile(
        r"^https?://(?:"
        r"images\.unsplash\.com/(?:photo|flagged/photo)-[a-zA-Z0-9_-]+|"
        r"plus\.unsplash\.com/premium_photo-[a-zA-Z0-9_-]+|"
        r"pbs\.twimg\.com/media/[a-zA-Z0-9_-]+|"
        r"i\.imgur\.com/[a-zA-Z0-9_-]+|"
        r"media\d*\.giphy\.com/media/[a-zA-Z0-9_/-]+|"
        r"picsum\.photos/[^\s<>\"')]+"
        r")(?:[?#][^\s<>\"')]*)?$",
        re.IGNORECASE,
    )
    QUERY_IMG_FORMAT_RE = re.compile(
        r"[?&](?:format|ext|fm)=(?:jpg|jpeg|png|webp|gif|avif)(?:&|$)",
        re.IGNORECASE,
    )

    def __init__(self, full_text, eng_font, hin_font, is_streaming=False):
        super().__init__()
        self.full_text = str(full_text or "")
        self.eng_font = eng_font
        self.hin_font = hin_font
        self.is_streaming = bool(is_streaming)
        self.protected_elements = {}
        self.code_snippets = []
        self.is_cancelled = False

    def protect_block(self, html):
        token = f"<jarvis-token-{len(self.protected_elements)}/>"
        self.protected_elements[token] = html
        return f"\n\n{token}\n\n"

    def protect_inline(self, html):
        token = f"<jarvis-token-{len(self.protected_elements)}/>"
        self.protected_elements[token] = html
        return token

    def strip_leading_emotion_tag(self, text):
        return re.sub(r"^\s*\[([a-zA-Z_ -]{2,20})\]\s*", "", text, count=1)

    def is_image_url(self, url):
        clean = str(url or "").strip()
        if not clean:
            return False
        if self.IMAGE_EXT_RE.search(clean):
            return True
        if self.KNOWN_IMG_HOST_RE.match(clean):
            return True
        if clean.startswith(("http://", "https://")) and self.QUERY_IMG_FORMAT_RE.search(clean):
            return True
        return False

    def format_local_or_web_url(self, url):
        formatted_url = str(url or "").strip()
        if formatted_url.startswith(("http://", "https://", "file://")):
            return formatted_url
        raw_path = formatted_url.replace("\\", "/")
        encoded_path = urllib.parse.quote(raw_path, safe=":/")
        if re.match(r"^[a-zA-Z]:", formatted_url):
            return "file:///" + encoded_path
        return "file://" + encoded_path

    def build_image_card_html(self, img_url, alt="img_preview", caption_text="", caption_url=""):
        safe_url = self.format_local_or_web_url(img_url)
        encoded = _encode_resource_payload(safe_url)
        encoded_preview = _encode_resource_payload(safe_url)
        header_html = ""
        if caption_text and caption_url:
            header_html = (
                f'<p style="margin-top: 8px; margin-bottom: 4px; line-height: 1.35;">'
                f'<a href="{caption_url}" style="text-decoration:none; color:#C48AF9; '
                f'font-weight:600;">{caption_text} ↗</a></p>'
            )
        card_html = (
            f'{header_html}'
            f'<p style="margin-top: 6px; margin-bottom: 6px; line-height: 100%;">'
            f'<a href="imgpreview:{encoded_preview}" style="text-decoration:none;">'
            f'<img src="img:{encoded}" width="{self.IMG_W}" height="{self.IMG_H}" alt="{alt}"></a></p>'
        )
        return self.protect_block(card_html)

    def build_preview_card_html(self, url, caption_text=""):
        encoded = _encode_resource_payload(url)
        header_html = ""
        if caption_text:
            header_html = (
                f'<p style="margin-top: 8px; margin-bottom: 4px; line-height: 1.35;">'
                f'<a href="{url}" style="text-decoration:none; color:#C48AF9; '
                f'font-weight:600;">{caption_text} ↗</a></p>'
            )
        card_html = (
            f'{header_html}'
            f'<p style="margin-top: 6px; margin-bottom: 6px; line-height: 100%;">'
            f'<a href="{url}" style="text-decoration:none;">'
            f'<img src="preview:{encoded}" width="{self.CARD_W}" height="{self.CARD_H}" alt="link_preview"></a></p>'
        )
        return self.protect_block(card_html)

    def build_loading_card_html(self, kind="preview"):
        if kind == "image":
            return self.protect_block(
                f'<p style="margin-top: 6px; margin-bottom: 6px; line-height: 100%;">'
                f'<img src="loading://image" width="{self.IMG_W}" height="{self.IMG_H}" alt="loading_image"></p>'
            )
        return self.protect_block(
            f'<p style="margin-top: 6px; margin-bottom: 6px; line-height: 100%;">'
            f'<img src="loading://preview" width="{self.CARD_W}" height="{self.CARD_H}" alt="loading_preview"></p>'
        )

    def normalize_streaming_fences(self, text):
        fence_matches = list(re.finditer(r"(?m)^[ ]{0,3}```", text))
        if len(fence_matches) % 2 == 1:
            return text + "\n```"
        return text

    def stabilize_streaming_tail(self, text):
        if not self.is_streaming or not text:
            return text

        text = re.sub(
            r"!\[[^\]]*\]\([^\)\s]*$",
            lambda _: self.build_loading_card_html("image"),
            text,
        )
        text = re.sub(
            r"!\[[^\]]*$",
            lambda _: self.build_loading_card_html("image"),
            text,
        )

        def tail_md_link_replacer(match):
            partial_url = match.group(1)
            if self.is_image_url(partial_url):
                return self.build_loading_card_html("image")
            return self.build_loading_card_html("preview")

        text = re.sub(r"\[[^\]]+\]\((https?://[^\)\s]*)$", tail_md_link_replacer, text)

        def tail_raw_url_replacer(match):
            partial_url = match.group(1)
            if self.is_image_url(partial_url):
                return self.build_loading_card_html("image")
            return self.build_loading_card_html("preview")

        text = re.sub(r'(?<!=["\'])(https?://[^\s<>"\')]+)$', tail_raw_url_replacer, text)
        return text

    def process_markdown_code_blocks(self, text):
        pattern = r"(?m)^[ ]{0,3}```([^\n]*)\n(.*?)^[ ]{0,3}```"

        def replacer(match):
            lang = match.group(1).strip().lower()
            raw_code = match.group(2).rstrip("\n")
            code_idx = len(self.code_snippets)
            self.code_snippets.append(raw_code)

            formatter = HtmlFormatter(style="monokai", noclasses=True, nowrap=True)

            if not lang:
                lang = "code"
            try:
                lexer = get_lexer_by_name(lang, stripall=False)
            except pygments.util.ClassNotFound:
                lexer = get_lexer_by_name("text")

            highlighted = highlight(raw_code, lexer, formatter)
            html = (
                f'<table width="100%" cellspacing="0" cellpadding="0" bgcolor="#121318" '
                f'style="margin-top: 10px; margin-bottom: 12px;">'
                f'<tr><td bgcolor="#1C1D26" style="padding: 8px 14px;">'
                f'<table width="100%" cellspacing="0" cellpadding="0" style="margin:0; border:none;">'
                f'<tr>'
                f'<td align="left" style="border:none; padding:0;">'
                f'<span style="color: #9496A6; font-size: 8.5pt; font-weight: 700; '
                f'font-family: \'{self.eng_font}\', sans-serif; letter-spacing: 1.2px;">{lang.upper()}</span>'
                f'</td>'
                f'<td align="right" style="border:none; padding:0;">'
                f'<a href="copycode://{code_idx}" style="color: #B4B6C8; text-decoration: none; '
                f'font-size: 8.5pt; font-weight: 600; font-family: \'{self.eng_font}\', sans-serif;">Copy</a>'
                f'</td>'
                f'</tr></table>'
                f'</td></tr>'
                f'<tr><td style="padding: 12px 15px;">'
                f'<pre style="margin: 0; font-family: \'Cascadia Code\', Consolas, monospace; '
                f'font-size: 10.2pt; line-height: 1.45; color: #E5E5EA; white-space: pre-wrap; word-wrap: break-word;">'
                f'{highlighted}</pre>'
                f'</td></tr></table>'
            )
            return self.protect_block(html)

        return re.sub(pattern, replacer, text, flags=re.DOTALL)

    def process_md_images(self, text):
        pattern = r"!\[([^\]]*)\]\(([^)]+)\)"

        def replacer(match):
            alt, url = match.groups()
            clean_url = url.strip().strip("\"'")
            return self.build_image_card_html(clean_url, alt=alt or "img_preview")

        return re.sub(pattern, replacer, text)

    def process_md_links(self, text):
        pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def replacer(match):
            display_text, url = match.groups()
            url = url.strip().strip("\"'")

            if "<jarvis-token-" in display_text:
                return self.protect_block(
                    f'<p style="margin-top: 6px; margin-bottom: 6px; line-height: 100%;"><a href="{url}">{display_text}</a></p>'
                )

            if "youtube.com" in url or "youtu.be" in url:
                yt_match = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([a-zA-Z0-9_-]{11})", url)
                if yt_match:
                    vid_id = yt_match.group(1)
                    return self.protect_block(
                        f'<p style="margin-top: 8px; margin-bottom: 4px; line-height: 1.35;">'
                        f'<a href="{url}" style="text-decoration:none; color:#C48AF9; font-weight:600;">{display_text} ↗</a></p>'
                        f'<p style="margin-top: 4px; margin-bottom: 6px; line-height: 100%;">'
                        f'<a href="{url}" style="text-decoration:none;">'
                        f'<img src="img:{_encode_resource_payload(f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg")}" width="{self.IMG_W}" height="{self.IMG_H}" alt="yt_preview"></a></p>'
                    )

            clean_disp = display_text.strip()
            if self.is_image_url(url):
                if clean_disp == url or clean_disp.startswith(("http://", "https://", "file://")):
                    return self.build_image_card_html(url, alt="img_preview")
                return self.build_image_card_html(url, alt=clean_disp, caption_text=clean_disp, caption_url=url)

            if url.startswith(("http://", "https://")):
                if clean_disp == url or clean_disp.startswith(("http://", "https://")):
                    return self.build_preview_card_html(url)
                return self.build_preview_card_html(url, caption_text=clean_disp)

            return self.protect_inline(
                f'<a href="{url}" style="color: #C48AF9; text-decoration: none; font-weight: 600;">{display_text} ↗</a>'
            )

        return re.sub(pattern, replacer, text)

    def process_raw_direct_images(self, text):
        web_pattern = (
            r'(?<!=["\'])(https?://[^\s<>"\')]+?\.(?:png|jpg|jpeg|gif|webp|bmp|svg|avif|ico|tiff)'
            r'(?:[?#][^\s<>"\')]*)?)(?!\))'
        )

        def web_replacer(match):
            url = match.group(1).rstrip(".,;)")
            return self.build_image_card_html(url, alt="img_preview")

        text = re.sub(web_pattern, web_replacer, text, flags=re.IGNORECASE)

        win_pattern = r'(?<!=["\'])([a-zA-Z]:[\\/][^\n<>"\']*?\.(?:png|jpg|jpeg|gif|webp|bmp|svg|avif))(?!\))'

        def win_replacer(match):
            raw_path = match.group(1).strip()
            return self.build_image_card_html(raw_path, alt="img_preview")

        return re.sub(win_pattern, win_replacer, text, flags=re.IGNORECASE)

    def process_youtube_links(self, text):
        pattern = (
            r'(?<!=["\'])(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)'
            r'([a-zA-Z0-9_-]{11})(?:[&?][a-zA-Z0-9_=%&.-]*)?)'
        )
        return re.sub(
            pattern,
            lambda m: self.protect_block(
                f'<p style="margin-top: 6px; margin-bottom: 6px; line-height: 100%;">'
                f'<a href="{m.group(1)}" style="text-decoration:none;">'
                f'<img src="img:{_encode_resource_payload(f"https://img.youtube.com/vi/{m.group(2)}/maxresdefault.jpg")}" width="{self.IMG_W}" height="{self.IMG_H}" alt="yt_preview"></a></p>'
            ),
            text,
        )

    def process_raw_links(self, text):
        pattern = r'(?<!=["\'])(https?://[^\s<>"\']+)'

        def replacer(match):
            url = match.group(1).rstrip(".,;)")
            if self.is_image_url(url):
                return self.build_image_card_html(url, alt="img_preview")
            return self.build_preview_card_html(url)

        return re.sub(pattern, replacer, text)

    def promote_first_paragraph(self, md_html):
        match = re.search(r"<p(\s[^>]*)?>", md_html)
        if not match:
            return md_html
        inline_style = (
            'style="font-size: 13.2pt; color: #FFFFFF; font-weight: 500; '
            'line-height: 1.5; margin-bottom: 10px;"'
        )
        if match.group(1):
            replacement = f"<p{match.group(1)} {inline_style}>"
        else:
            replacement = f"<p {inline_style}>"
        return md_html[:match.start()] + replacement + md_html[match.end():]

    def get_styled_html(self, content):
        return f"""
        <html><head><style>
            body {{
                margin: 0px;
                padding: 0px;
                color: #ECECF2;
                font-family: '{self.eng_font}', '{self.hin_font}', 'Segoe UI', sans-serif;
                font-size: 12pt;
                line-height: 1.56;
                word-wrap: break-word;
            }}
            h1 {{
                font-size: 16.5pt;
                color: #FFFFFF;
                font-weight: 700;
                margin-top: 18px;
                margin-bottom: 8px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                padding-bottom: 5px;
            }}
            h2 {{
                font-size: 14.2pt;
                color: #F7F7FC;
                font-weight: 700;
                margin-top: 14px;
                margin-bottom: 6px;
            }}
            h3 {{
                font-size: 12.6pt;
                color: #E2E2F0;
                font-weight: 600;
                margin-top: 10px;
                margin-bottom: 5px;
            }}
            p {{
                margin-top: 0px;
                margin-bottom: 8px;
            }}
            blockquote {{
                margin: 8px 0px 10px 0px;
                padding: 8px 14px;
                border-left: 3px solid #BF5AF2;
                background-color: rgba(191, 90, 242, 0.085);
                color: #DCDCE8;
                font-style: italic;
            }}
            ul, ol {{
                margin-top: 3px;
                margin-bottom: 8px;
                padding-left: 22px;
            }}
            li {{
                margin-bottom: 4px;
            }}
            hr {{
                border: none;
                border-top: 1px solid rgba(255,255,255,0.08);
                margin: 10px 0px;
            }}
            table {{
                border-collapse: collapse;
                margin-top: 6px;
                margin-bottom: 10px;
                width: 100%;
            }}
            th, td {{
                border: 1px solid rgba(255,255,255,0.09);
                padding: 8px 11px;
                text-align: left;
                font-size: 11pt;
            }}
            th {{
                background-color: rgba(255,255,255,0.065);
                font-weight: 700;
                color: #FFFFFF;
            }}
            strong, b {{
                color: #FFFFFF;
                font-weight: 700;
            }}
            code {{
                background-color: #21222C;
                color: #E6A8FA;
                font-family: 'Cascadia Code', Consolas, monospace;
                font-size: 10.4pt;
            }}
            pre code {{
                background-color: transparent;
            }}
            a {{
                color: #C48AF9;
                text-decoration: none;
                font-weight: 600;
            }}
        </style></head><body>{content}</body></html>
        """

    def run(self):
        if self.is_cancelled:
            return

        text = self.strip_leading_emotion_tag(self.full_text)
        text = self.normalize_streaming_fences(text)
        text = self.process_markdown_code_blocks(text)
        text = self.stabilize_streaming_tail(text)
        text = self.process_md_images(text)
        text = self.process_md_links(text)
        text = self.process_raw_direct_images(text)
        text = self.process_youtube_links(text)
        text = self.process_raw_links(text)

        md_html = markdown(
            text,
            extras=[
                "tables",
                "cuddled-lists",
                "strike",
                "break-on-newline",
                "html-classes",
                "fenced-code-blocks",
            ],
        )

        md_html = re.sub(
            r"<code>([^<\n]+?)</code>",
            r"<code>&nbsp;\1&nbsp;</code>",
            md_html,
        )
        md_html = re.sub(r"<p>\s*(?:<br\s*/?>\s*)*(<jarvis-token-\d+/>)\s*(?:<br\s*/?>\s*)*</p>", r"\1", md_html)

        for token, value in self.protected_elements.items():
            md_html = md_html.replace(token, value)

        md_html = re.sub(r"(?:<p>\s*</p>\s*)+$", "", md_html.strip())
        md_html = self.promote_first_paragraph(md_html)

        if self.is_cancelled:
            return

        final_html = self.get_styled_html(md_html)
        if not self.is_cancelled:
            self.finished_signal.emit(self.code_snippets, final_html)