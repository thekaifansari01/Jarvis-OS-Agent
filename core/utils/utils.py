import re
from typing import List


def clean_and_split_apps(raw: str) -> List[str]:
    raw = re.sub(r"\b(and|then|also|print|with|comma|aur|phir|aur bhi)\b", ",", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+", " ", raw).strip()
    parts = re.split(r",|\s+", raw)
    return [p.strip().lower() for p in parts if p.strip()]


def resolve_pronouns(command: str, memory_instance=None) -> str:
    return command