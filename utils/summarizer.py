from typing import List
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer
from .logger import get_logger

logger = get_logger("SUM", __name__)

def cheap_summarize(text: str, max_sentences: int = 3) -> str:
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LexRankSummarizer()
        sentences = summarizer(parser.document, max_sentences)
        return " ".join(str(s) for s in sentences)
    except Exception:
        # Fallback: naive first N sentences
        logger.warning("sumy unavailable or failed; using naive summarization fallback.")
        parts = text.split(". ")
        return ". ".join(parts[:max_sentences])