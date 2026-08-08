import re
import urllib.parse
import pygments.util
from PyQt5.QtCore import QThread, pyqtSignal
from markdown2 import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

class ParserWorker(QThread):
    finished_signal = pyqtSignal(list, str)

    def __init__(self, full_text, eng_font, hin_font):
        super().__init__()
        self.full_text = full_text
        self.eng_font = eng_font
        self.hin_font = hin_font
        self.protected_elements = {}
        self.is_cancelled = False

    def protect(self, html):
        token = f"<jarvis-token-{len(self.protected_elements)}/>"
        self.protected_elements[token] = html
        return token

    def process_markdown_code_blocks(self, text):
        pattern = r'(?m)^[ ]{0,3}```([^\n]*)\n(.*?)^[ ]{0,3}```'
        def replacer(match):
            lang = match.group(1).strip().lower()
            raw_code = match.group(2)
            formatter = HtmlFormatter(style='monokai', noclasses=True, nowrap=True)
            
            if not lang:
                lang = "text"
            try:
                lexer = get_lexer_by_name(lang, stripall=True)
            except pygments.util.ClassNotFound:
                lexer = get_lexer_by_name("text")
                lang = "text"
                    
            highlighted = highlight(raw_code, lexer, formatter)
            html = f'<table width="100%" cellspacing="0" cellpadding="1" bgcolor="#44444C" style="margin-top: 14px; margin-bottom: 14px; border-radius: 8px;"><tr><td><table width="100%" cellspacing="0" cellpadding="0" bgcolor="#1A1A1D" style="border-radius: 8px;"><tr><td bgcolor="#2D2D30" style="padding: 8px 12px; border-top-left-radius: 8px; border-top-right-radius: 8px;"><span style="color:#FF5F56; font-size:16px;">●</span>&nbsp;<span style="color:#FFBD2E; font-size:16px;">●</span>&nbsp;<span style="color:#27C93F; font-size:16px;">●</span>&nbsp;&nbsp;&nbsp;&nbsp;<span style="color: #999999; font-size: 11px; font-weight: bold; font-family: sans-serif;">{lang.upper()}</span></td></tr><tr><td style="padding: 12px;"><pre style="margin: 0; font-family: Consolas, monospace; font-size: 11pt; color: #D4D4D4; white-space: pre-wrap; word-wrap: break-word;">{highlighted}</pre></td></tr></table></td></tr></table>'
            return self.protect(html)
        return re.sub(pattern, replacer, text, flags=re.DOTALL)

    def process_md_images(self, text):
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        def replacer(match):
            alt, url = match.groups()
            formatted_url = url
            if not formatted_url.startswith('http'):
                raw_path = formatted_url.replace('\\', '/')
                encoded_path = urllib.parse.quote(raw_path, safe=":/")
                formatted_url = "file:///" + encoded_path if re.match(r'^[a-zA-Z]:', formatted_url) else "file://" + encoded_path
            return self.protect(f'<img src="{formatted_url}" width="380" alt="{alt}">')
        return re.sub(pattern, replacer, text)

    def process_md_links(self, text):
        pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        def replacer(match):
            display_text, url = match.groups()
            if "<jarvis-token-" in display_text:
                return self.protect(f'<p style="margin-top: 10px;"><a href="{url}">{display_text}</a></p>')
            if "youtube.com" in url or "youtu.be" in url:
                yt_match = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
                if yt_match:
                    vid_id = yt_match.group(1)
                    return self.protect(
                        f'<p style="margin-top: 12px; margin-bottom: 4px; line-height: 1.3;">'
                        f'<a href="{url}" style="text-decoration:none; color:inherit;">'
                        f'<img src="https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg" width="380" height="214" alt="yt_preview"><br>'
                        f'<span style="color: #FFFFFF; font-size: 11pt; font-weight: bold;">{display_text}</span><br>'
                        f'<span style="color: #A0A0A5; font-size: 9pt;">🔗 youtube.com</span></a></p>'
                    )
            domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
            return self.protect(
                f'<p style="margin-top: 12px; margin-bottom: 4px; line-height: 1.3;">'
                f'<a href="{url}" style="text-decoration:none; color:inherit;">'
                f'<img src="preview://{url}" width="380" alt="link_preview"><br>'
                f'<span style="color: #FFFFFF; font-size: 11pt; font-weight: bold;">{display_text}</span><br>'
                f'<span style="color: #A0A0A5; font-size: 9pt;">🔗 {domain}</span></a></p>'
            )
        return re.sub(pattern, replacer, text)

    def process_raw_direct_images(self, text):
        web_pattern = r'(?<!=["\'])(https?://[^\s<>"\']+?\.(?:png|jpg|jpeg|gif|webp))(?!\))'
        text = re.sub(web_pattern, lambda m: self.protect(f'<p style="margin-top: 10px;"><a href="{m.group(1)}"><img src="{m.group(1)}" width="380" alt="img_preview"></a></p>'), text, flags=re.IGNORECASE)
        win_pattern = r'(?<!=["\'])([a-zA-Z]:[\\/][^\n<>"]+?\.(?:png|jpg|jpeg|gif|webp))(?!\))'
        def win_replacer(m):
            raw_path = m.group(1).replace(chr(92), "/")
            encoded_path = urllib.parse.quote(raw_path, safe=":/")
            return self.protect(f'<p style="margin-top: 10px;"><a href="file:///{encoded_path}"><img src="file:///{encoded_path}" width="380" alt="img_preview"></a></p>')
        return re.sub(win_pattern, win_replacer, text, flags=re.IGNORECASE)

    def process_youtube_links(self, text):
        pattern = r'(?<!=["\'])(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})(?:[&?][a-zA-Z0-9_=.-]*)?)'
        return re.sub(pattern, lambda m: self.protect(f'<p style="margin-top: 10px; margin-bottom: 2px; line-height: 1.0;"><a href="{m.group(1)}"><img src="https://img.youtube.com/vi/{m.group(2)}/maxresdefault.jpg" width="380" height="214" alt="yt_preview"></a></p>'), text)

    def process_raw_links(self, text):
        pattern = r'(?<!=["\'])(https?://[^\s<>"\']+)'
        def replacer(match):
            url = match.group(1)
            domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
            return self.protect(
                f'<p style="margin-top: 12px; margin-bottom: 4px; line-height: 1.3;">'
                f'<a href="{url}" style="text-decoration:none; color:inherit;">'
                f'<img src="preview://{url}" width="380" alt="link_preview"><br>'
                f'<span style="color: #FFFFFF; font-size: 11pt; font-weight: bold;">{url}</span><br>'
                f'<span style="color: #A0A0A5; font-size: 9pt;">🔗 {domain}</span></a></p>'
            )
        return re.sub(pattern, replacer, text)

    def get_styled_html(self, content):
        return f"""
        <html><head><style>
            body {{ 
                margin: 0px; padding: 0px; 
                color: #E0E0E6; 
                font-family: '{self.eng_font}', '{self.hin_font}', sans-serif; 
                font-size: 13pt; 
                line-height: 1.65;
                word-wrap: break-word; 
            }}
            h1 {{ font-size: 20pt; color: #FFFFFF; font-weight: 800; margin-top: 16px; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 8px; letter-spacing: 0.5px; }}
            h2 {{ font-size: 17pt; color: #F5F5FA; font-weight: 700; margin-top: 14px; margin-bottom: 10px; }}
            h3 {{ font-size: 14pt; color: #DADAEE; font-weight: 600; margin-top: 12px; margin-bottom: 8px; }}
            p {{ margin-top: 0px; margin-bottom: 14px; }}
            blockquote {{ 
                margin: 10px 0px 16px 0px; 
                padding: 10px 16px; 
                border-left: 3px solid #D67CFF; 
                color: rgba(224, 224, 230, 0.85); 
                font-style: italic; 
                background: linear-gradient(90deg, rgba(191, 90, 242, 0.08) 0%, transparent 100%);
                border-radius: 0px 8px 8px 0px; 
            }}
            ul, ol {{ margin-top: 4px; margin-bottom: 14px; padding-left: 24px; }}
            li {{ margin-bottom: 8px; }}
            hr {{ border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 18px 0px; }}
            table {{ border-collapse: collapse; margin-bottom: 16px; width: 100%; border-radius: 8px; overflow: hidden; }}
            th, td {{ border: 1px solid rgba(255,255,255,0.08); padding: 12px; text-align: left; font-size: 12pt; }}
            th {{ background-color: rgba(255,255,255,0.05); font-weight: 700; color: #FFF; }}
            strong, b {{ color: #FFFFFF; font-weight: 700; }}
            code {{ background-color: #1C1C20; color: #E5A4FA; padding: 3px 6px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05); font-family: Consolas, monospace; font-size: 11.5pt; }}
            pre code {{ background-color: transparent; padding: 0; border: none; }}
            a {{ color: #D67CFF; text-decoration: none; font-weight: 600; }}
            img {{ display: block; margin-bottom: 0px; max-width: 100%; border-radius: 8px; }}
        </style></head><body>{content}</body></html>
        """

    def run(self):
        if self.is_cancelled:
            return
        text = self.process_markdown_code_blocks(self.full_text)
        text = self.process_md_images(text)
        text = self.process_md_links(text)
        text = self.process_raw_direct_images(text)
        text = self.process_youtube_links(text)
        text = self.process_raw_links(text)
        
        md_html = markdown(text, extras=["tables", "cuddled-lists", "strike", "break-on-newline", "html-classes", "fenced-code-blocks"])
        md_html = re.sub(r'<p>\s*(<jarvis-token-\d+/>)\s*</p>', r'\1', md_html)
        
        for token, value in self.protected_elements.items():
            md_html = md_html.replace(token, value)
                
        if self.is_cancelled:
            return

        html_tokens = re.split(r'(<[^>]+>)', md_html)
        html_tokens = [t for t in html_tokens if t]
        
        final_html = self.get_styled_html(md_html)
        if not self.is_cancelled:
            self.finished_signal.emit(html_tokens, final_html)