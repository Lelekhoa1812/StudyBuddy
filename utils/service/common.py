import re
import unicodedata
from utils.logger import get_logger

logger = get_logger("COMMON", __name__)

def split_sentences(text: str):
    return re.split(r"(?<=[\.\!\?])\s+", text.strip())

def slugify(value: str):
    value = str(value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)

def trim_text(s: str, n: int):
    s = s or ""
    if len(s) <= n:
        return s
    return s[:n] + "…"