import re
import html

from ..core.FontRegistry import get_code_font
from ..core.Theme import (
    SYNTAX_TOKENS, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_BODY,
    SURFACE_CODE_BG,
)


class MarkdownRenderer:
    TOKEN_MASTER_RE = re.compile(
        r'(?P<shebang>^#![^\n]*)'
        r'|(?P<preproc>^[ \t]*#[ \t]*(?:include|define|ifdef|ifndef|endif|pragma|undef|error|warning|line)\b[^\n]*)'
        r'|(?P<attribute>#\[[^\]\n]*\])'
        r'|(?P<private>#[A-Za-z_]\w*)'
        r'|(?P<comment>#[ \t][^\n]*|#(?=\n|$)[^\n]*|//[^\n]*|/\*[\s\S]*?\*/)'
        r'|(?P<string>"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
        r'|(?P<decorator>@[a-zA-Z_]\w*)'
        r'|(?P<keyword>(?i:\b(?:def|class|return|if|elif|else|for|while|try|except|finally|with|as|import|from|pass|break|continue|and|or|not|in|is|lambda|yield|async|await|true|false|none|const|let|var|function|export|default|switch|case|new|this|typeof|instanceof|null|undefined|static|interface|type|struct|enum|pub|fn|impl|use|mod|match|where|trait|mut|ref|crate|template|typename|namespace|constexpr|public|private|protected|using|concept|requires|noexcept|auto|void|func|package|go|chan|defer|range|map|local|readonly|declare|select|insert|update|delete|create|table|drop|alter|raise|global|nonlocal|del|assert|recursive|left|right|inner|outer|join|on|group|by|having|limit|offset|union|all|distinct|into|values|set|begin|commit|rollback|transaction|primary|foreign|key|references|index|view|trigger|fi|done|then|until|esac)\b))'
        r'|(?P<builtin>(?i:\b(?:self|cls|print|len|range|enumerate|zip|map|filter|int|str|float|list|dict|set|tuple|bool|super|open|isinstance|getattr|setattr|hasattr|Exception|ValueError|TypeError|KeyError|RuntimeError|console|window|document|Promise|JSON|Math|Object|Array|sum|count|avg|min|max|rank|lag|lead|over|partition|coalesce|nullif|round|make|append|println|printf|sprintf|errorf|now|sleep)\b))'
        r'|(?P<func>\b[a-zA-Z_]\w*(?=\s*\())'
        r'|(?P<number>\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b)',
        re.MULTILINE
    )

    FENCE_LINE_RE = re.compile(r"(?m)^[ \t]*```([a-zA-Z0-9_+#.-]*)[ \t\r]*$")
    CODE_BLOCK_RE = re.compile(
        r"(?m)^[ \t]*```([a-zA-Z0-9_+#.-]*)[ \t\r]*\n?(.*?)^[ \t]*```[ \t\r]*$",
        re.DOTALL,
    )
    INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
    LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
    IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\s]+)\)")
    BOLD_ITALIC_RE = re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*")
    BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
    ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*|\s)(.+?)(?<!\*|\s)\*(?!\*)")
    STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
    BULLET_RE = re.compile(r"^(\s*)[-*•]\s+(.+)$")
    NUMBERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
    BLOCKQUOTE_RE = re.compile(r"^((?:>[ \t]*)+)(.*)$")
    TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
    TABLE_SEP_RE = re.compile(r"^\s*\|(?=[\s:|\-]*-)[\s:|\-]+\|\s*$")
    LONG_TOKEN_RE = re.compile(r"\S{65,}")

    _highlight_cache = {}
    _code_line_cache = {}
    _html_cache = {}
    _line_cache = {}
    _HTML_CACHE_LIMIT = 120
    _HIGHLIGHT_CACHE_LIMIT = 200
    _CODE_LINE_CACHE_LIMIT = 2000
    _LINE_CACHE_LIMIT = 1500

    @classmethod
    def _evict_oldest(cls, cache_dict, limit):
        while len(cache_dict) > limit:
            cache_dict.pop(next(iter(cache_dict)))

    @classmethod
    def _soft_wrap_long_tokens(cls, text: str) -> str:
        if len(text) < 65:
            return text
        def inject_zwsp(match):
            s = match.group(0)
            return "\u200b".join(s[i:i + 45] for i in range(0, len(s), 45))
        return cls.LONG_TOKEN_RE.sub(inject_zwsp, text)

    @classmethod
    def _apply_bold_italic(cls, text: str) -> str:
        if "*" not in text and "_" not in text and "~" not in text:
            return text
        text = cls.BOLD_ITALIC_RE.sub(
            f'<b style="color: {TEXT_PRIMARY};"><i>\\1</i></b>', text
        )
        text = cls.STRIKE_RE.sub(
            f'<s style="color: {TEXT_SECONDARY};">\\1</s>', text
        )
        text = cls.BOLD_RE.sub(
            lambda m: f'<b style="color: {TEXT_PRIMARY};">{m.group(1) or m.group(2)}</b>',
            text,
        )
        text = cls.ITALIC_RE.sub(
            f'<i style="color: {TEXT_SECONDARY};">\\1</i>', text
        )
        return text

    @classmethod
    def auto_heal_markdown(cls, text: str) -> str:
        if len(cls.FENCE_LINE_RE.findall(text)) % 2 != 0:
            return text + "\n```"

        last_nl = text.rfind("\n")
        if last_nl != -1:
            last_line = text[last_nl + 1:].strip()
            if last_line.startswith("|") and not last_line.endswith("|"):
                prev_nl = text.rfind("\n", 0, last_nl)
                prev_line = text[prev_nl + 1:last_nl].strip()
                if cls.TABLE_ROW_RE.match(prev_line):
                    if all(c in " -:|" for c in last_line):
                        return text + " - |"
                    return text + " |"
        return text

    @classmethod
    def highlight_code(cls, code: str) -> str:
        result = []
        last_idx = 0

        for match in cls.TOKEN_MASTER_RE.finditer(code):
            start, end = match.span()
            if start > last_idx:
                chunk = code[last_idx:start]
                result.append(html.escape(chunk))
            group_name = match.lastgroup
            token_text = html.escape(match.group(0))
            style = SYNTAX_TOKENS.get(group_name, SYNTAX_TOKENS["default"])
            result.append(f'<span style="{style}">{token_text}</span>')
            last_idx = end

        if last_idx < len(code):
            chunk = code[last_idx:]
            result.append(html.escape(chunk))

        highlighted = "".join(result)
        return highlighted.replace("\t", "    ")

    @classmethod
    def _highlight_code_line(cls, line: str) -> str:
        if not line:
            return ""
        cached = cls._code_line_cache.get(line)
        if cached is not None:
            return cached
        res = cls.highlight_code(line)
        cls._code_line_cache[line] = res
        cls._evict_oldest(cls._code_line_cache, cls._CODE_LINE_CACHE_LIMIT)
        return res

    @classmethod
    def highlight_code_cached(cls, code: str) -> str:
        key = (code, get_code_font())
        cached = cls._highlight_cache.get(key)
        if cached is not None:
            return cached

        if '"""' not in code and "'''" not in code and "/*" not in code:
            result = "\n".join(cls._highlight_code_line(ln) for ln in code.split("\n"))
        else:
            result = cls.highlight_code(code)

        cls._highlight_cache[key] = result
        cls._evict_oldest(cls._highlight_cache, cls._HIGHLIGHT_CACHE_LIMIT)
        return result

    @classmethod
    def format_inline(cls, text: str, accent_hex: str = "rgb(191, 90, 242)") -> str:
        inline_vault = []
        link_vault = []
        image_vault = []
        code_family = get_code_font()

        def save_inline_code(m):
            idx = len(inline_vault)
            code_content = html.escape(m.group(1))
            inline_vault.append(
                f'<span style="background-color: rgba(255, 255, 255, 0.11); '
                f'color: {SYNTAX_TOKENS["keyword"].split("color: ")[1].split(";")[0]}; '
                f'font-family: \'{code_family}\', \'Consolas\', monospace; '
                f'font-size: 9.5pt;">&nbsp;{code_content}&nbsp;</span>'
            )
            return f"@@INLINECODE_{idx}@@"

        def save_image(m):
            idx = len(image_vault)
            alt_text = html.escape(m.group(1) or "image")
            safe_url = html.escape(m.group(2), quote=True)
            image_vault.append(
                f'<a href="{safe_url}" style="color: {accent_hex}; '
                f'text-decoration: underline; font-style: italic;">🖼 {alt_text}</a>'
            )
            return f"@@IMAGE_{idx}@@"

        def save_link(m):
            idx = len(link_vault)
            raw_text = html.escape(m.group(1))
            styled_text = cls._apply_bold_italic(raw_text)
            safe_url = html.escape(m.group(2), quote=True)
            link_vault.append(
                f'<a href="{safe_url}" style="color: {accent_hex}; '
                f'text-decoration: underline; font-weight: 500;">{styled_text}</a>'
            )
            return f"@@LINK_{idx}@@"

        processed = cls.INLINE_CODE_RE.sub(save_inline_code, text) if "`" in text else text
        if "![" in processed:
            processed = cls.IMAGE_RE.sub(save_image, processed)
        if "[" in processed:
            processed = cls.LINK_RE.sub(save_link, processed)
        processed = html.escape(cls._soft_wrap_long_tokens(processed))
        processed = cls._apply_bold_italic(processed)

        for idx, link_html in enumerate(link_vault):
            processed = processed.replace(f"@@LINK_{idx}@@", link_html)

        for idx, img_html in enumerate(image_vault):
            processed = processed.replace(f"@@IMAGE_{idx}@@", img_html)

        for idx, badge_html in enumerate(inline_vault):
            processed = processed.replace(f"@@INLINECODE_{idx}@@", badge_html)

        return processed

    @classmethod
    def _render_table_html(cls, headers, rows, accent_hex: str) -> str:
        td_style = (
            'border: 1px solid rgba(255, 255, 255, 0.12); '
            'padding: 5px 10px; text-align: left; font-size: 9pt; '
            f'color: {TEXT_BODY};'
        )
        th_style = (
            'border: 1px solid rgba(255, 255, 255, 0.12); '
            'padding: 5px 10px; text-align: left; font-size: 9pt; '
            'font-weight: bold; color: #FFFFFF; '
            'background-color: rgba(255, 255, 255, 0.06);'
        )
        col_count = max(1, len(headers))
        parts = [
            '<table cellspacing="0" cellpadding="0" '
            'style="border-collapse: collapse; margin: 6px 0px; '
            'border: 1px solid rgba(255, 255, 255, 0.12);">'
        ]
        parts.append('<tr>')
        for h in headers:
            h_html = cls.format_inline(h, accent_hex)
            parts.append(f'<th style="{th_style}">{h_html}</th>')
        parts.append('</tr>')
        for row in rows:
            parts.append('<tr>')
            normalized_row = (row + [""] * col_count)[:col_count]
            for cell in normalized_row:
                c_html = cls.format_inline(cell, accent_hex)
                parts.append(f'<td style="{td_style}">{c_html}</td>')
            parts.append('</tr>')
        parts.append('</table>')
        return "".join(parts)

    @classmethod
    def _render_single_line(cls, line: str, stripped: str, body_pt: int, accent_hex: str) -> str:
        cache_key = (line, body_pt, accent_hex, get_code_font())
        cached = cls._line_cache.get(cache_key)
        if cached is not None:
            return cached

        if not stripped:
            res = '<div style="height: 5px; font-size: 1pt;">&nbsp;</div>'
        elif stripped in ("---", "***", "___"):
            res = (
                '<hr style="border: none; background-color: rgba(255, 255, 255, 0.12); '
                'height: 1px; margin: 6px 0px;" />'
            )
        else:
            h_match = cls.HEADING_RE.match(stripped) if stripped.startswith("#") else None
            if h_match:
                level = len(h_match.group(1))
                h_text = cls.format_inline(h_match.group(2), accent_hex)
                h_size = max(body_pt, body_pt + (4 - level))
                h_color = TEXT_PRIMARY if level <= 2 else SYNTAX_TOKENS["builtin"].split("color: ")[1].split(";")[0]
                margin_top = 8 if level <= 2 else 5
                res = (
                    f'<div style="margin-top: {margin_top}px; margin-bottom: 3px; '
                    f'font-size: {h_size}pt; font-weight: bold; color: {h_color};">{h_text}</div>'
                )
            else:
                bq_match = cls.BLOCKQUOTE_RE.match(stripped) if stripped.startswith(">") else None
                if bq_match:
                    depth = bq_match.group(1).count(">")
                    q_content = bq_match.group(2).strip()
                    margin = 8 + (depth - 1) * 12
                    q_text = cls.format_inline(q_content, accent_hex)
                    res = (
                        f'<div style="margin: 3px 0px 3px {margin}px; color: rgba(210, 214, 235, 0.85); '
                        f'font-style: italic;"><span style="color: {accent_hex}; font-weight: bold;">'
                        f'▎ </span>{q_text}</div>'
                    )
                else:
                    b_match = cls.BULLET_RE.match(line)
                    if b_match:
                        indent_px = 6 + min(36, len(b_match.group(1)) * 6)
                        content = b_match.group(2)
                        marker = "•"
                        if content.startswith("[ ] "):
                            marker = "☐"
                            content = content[4:]
                        elif content[:4].lower() == "[x] ":
                            marker = "☑"
                            content = content[4:]
                        b_text = cls.format_inline(content, accent_hex)
                        res = (
                            f'<div style="margin-left: {indent_px}px; margin-top: 2px; margin-bottom: 2px;">'
                            f'<span style="color: {accent_hex}; font-weight: bold;">{marker}&nbsp;</span>{b_text}</div>'
                        )
                    else:
                        n_match = cls.NUMBERED_RE.match(line)
                        if n_match:
                            indent_px = 6 + min(36, len(n_match.group(1)) * 6)
                            num_str = n_match.group(2)
                            n_text = cls.format_inline(n_match.group(3), accent_hex)
                            res = (
                                f'<div style="margin-left: {indent_px}px; margin-top: 2px; margin-bottom: 2px;">'
                                f'<span style="color: {accent_hex}; font-weight: bold;">{num_str}.&nbsp;</span>{n_text}</div>'
                            )
                        else:
                            res = (
                                f'<div style="margin-top: 2px; margin-bottom: 2px; line-height: 1.46; '
                                f'word-wrap: break-word;">{cls.format_inline(line, accent_hex)}</div>'
                            )

        cls._line_cache[cache_key] = res
        cls._evict_oldest(cls._line_cache, cls._LINE_CACHE_LIMIT)
        return res

    @classmethod
    def to_html(cls, raw_text: str, font_family: str, base_pt: int, accent_rgb: list) -> str:
        if not raw_text.strip():
            return ""

        cache_key = (raw_text, font_family, base_pt, tuple(accent_rgb), get_code_font())
        cached = cls._html_cache.get(cache_key)
        if cached is not None:
            return cached

        result = cls._build_html(raw_text, font_family, base_pt, accent_rgb)
        cls._html_cache[cache_key] = result
        cls._evict_oldest(cls._html_cache, cls._HTML_CACHE_LIMIT)
        return result

    @classmethod
    def _build_html(cls, raw_text: str, font_family: str, base_pt: int, accent_rgb: list) -> str:
        clean = raw_text.strip()
        r, g, b = [max(0, min(255, int(c))) for c in accent_rgb]
        accent_hex = f"rgb({r}, {g}, {b})"
        code_family = get_code_font()

        healed = cls.auto_heal_markdown(clean)
        code_blocks = []

        def extract_code_block(match):
            lang = (match.group(1) or "code").strip().upper()
            raw_code = match.group(2).rstrip("\n")
            highlighted = cls.highlight_code_cached(raw_code)
            block_html = (
                f'<div style="background-color: {SURFACE_CODE_BG}; '
                f'font-family: \'{font_family}\', sans-serif; font-size: 7.5pt; '
                f'font-weight: bold; color: {accent_hex}; letter-spacing: 0.8px;">'
                f'{html.escape(lang)}</div>'
                f'<pre style="background-color: {SURFACE_CODE_BG}; margin: 0px; '
                f'font-family: \'{code_family}\', \'Consolas\', \'Courier New\', monospace; '
                f'font-size: 9.5pt; color: {SYNTAX_TOKENS["default"].split("color: ")[1].split(";")[0]}; '
                f'white-space: pre-wrap; word-wrap: break-word;">{highlighted}</pre>'
            )
            idx = len(code_blocks)
            code_blocks.append(block_html)
            return f"@@CODEBLOCK_{idx}@@"

        staged = cls.CODE_BLOCK_RE.sub(extract_code_block, healed) if "```" in healed else healed
        lines = staged.split("\n")
        out_lines = []
        body_pt = max(10, base_pt - 1)

        i = 0
        total = len(lines)
        while i < total:
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("@@CODEBLOCK_") and stripped.endswith("@@"):
                idx_str = stripped.replace("@@CODEBLOCK_", "").replace("@@", "")
                if idx_str.isdigit() and int(idx_str) < len(code_blocks):
                    out_lines.append(code_blocks[int(idx_str)])
                i += 1
                continue

            if "|" in stripped and cls.TABLE_ROW_RE.match(line) and i + 1 < total and cls.TABLE_SEP_RE.match(lines[i + 1]):
                header_cells = [c.strip() for c in stripped.strip("|").split("|")]
                i += 2
                table_rows = []
                while i < total and cls.TABLE_ROW_RE.match(lines[i]):
                    row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    table_rows.append(row_cells)
                    i += 1
                out_lines.append(cls._render_table_html(header_cells, table_rows, accent_hex))
                continue

            out_lines.append(cls._render_single_line(line, stripped, body_pt, accent_hex))
            i += 1

        body_html = "".join(out_lines)
        return (
            f'<div style="font-family: \'{font_family}\', \'Segoe UI\', sans-serif; '
            f'font-size: {body_pt}pt; font-weight: 450; color: {TEXT_BODY}; '
            f'border-left: 0px solid {accent_hex}; '
            f'text-align: left; padding-top: 2px;">{body_html}</div>'
        )