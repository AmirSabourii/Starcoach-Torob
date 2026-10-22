"""Persian/Arabic text normalization shared by ingest and search."""

from __future__ import annotations

import re

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_LETTER_MAP = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "ى": "ی",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
    }
)
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[0-9A-Za-z\u0600-\u06FF]+")

# Sentence glue. Dropped so a chat utterance still matches a product title.
# TODO: let the LLM emit a structured query and retire this list.
STOPWORDS = frozenset(
    {
        "و",
        "یا",
        "از",
        "به",
        "در",
        "با",
        "برای",
        "که",
        "این",
        "آن",
        "را",
        "رو",
        "یک",
        "یه",
        "می",
        "میخوام",
        "میخواهم",
        "خوام",
        "خواهم",
        "لطفا",
        "نزدیک",
        "اطراف",
        "فروشگاه",
        "مغازه",
        "قیمت",
        "خرید",
        "حضوری",
        "تو",
        "توی",
        "روی",
        "تا",
        "هم",
        "است",
        "هست",
        "داره",
        "داری",
        "بخر",
        "بگرد",
        "نشون",
        "بده",
        "کن",
        "کنید",
    }
)


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = text.strip()
    if not text or text.lower() == "null":
        return None
    return text


def normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def normalize_fa(value: object) -> str | None:
    """Fold Arabic yeh/kaf, ZWNJ, and digits so FTS and LIKE see one form."""
    text = clean_text(value)
    if text is None:
        return None
    text = text.translate(_LETTER_MAP).translate(_DIGIT_MAP)
    text = text.replace("\u200c", " ").replace("\u200d", "").replace("\ufeff", "")
    text = _WS.sub(" ", text).strip().casefold()
    return text or None


def tokenize(value: object) -> list[str]:
    text = normalize_fa(value) or ""
    tokens: list[str] = []
    for tok in _TOKEN.findall(text):
        if len(tok) < 2 or tok in STOPWORDS or tok in {"and", "or", "not"}:
            continue
        if tok not in tokens:
            tokens.append(tok)
        if len(tokens) >= 8:
            break
    return tokens


def parse_user_int(value: object) -> int | None:
    """Parse a filter number. Does not apply the dirty-price thresholds."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = normalize_digits(clean_text(value) or "")
        text = re.sub(r"[^\d.]", "", text)
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if number < 0 or number > 1e15:
        return None
    return int(number)


def like_contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
