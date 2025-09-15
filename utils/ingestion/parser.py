import io
from typing import List, Dict, Any
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import numpy as np
from ..logger import get_logger

logger = get_logger("PARSER", __name__)


def parse_pdf_bytes(b: bytes) -> List[Dict[str, Any]]:
    """
    Returns list of pages, each {'page_num': i, 'text': str, 'images': [PIL.Image]}
    """
    pages = []
    with fitz.open(stream=b, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text")
            images = []
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    # Convert CMYK/Alpha safely
                    if pix.n - pix.alpha >= 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    # Use PNG bytes to avoid 'not enough image data'
                    png_bytes = pix.tobytes("png")
                    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
                    images.append(im)
                except Exception as e:
                    logger.warning(f"Failed to extract image on page {i+1}: {e}")
                finally:
                    try:
                        pix = None
                    except Exception:
                        pass
            pages.append({"page_num": i + 1, "text": text, "images": images})
    logger.info(f"Parsed PDF with {len(pages)} pages")
    return pages


def parse_docx_bytes(b: bytes) -> List[Dict[str, Any]]:
    f = io.BytesIO(b)
    doc = Document(f)
    text = []
    images = []
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            data = rel.target_part.blob
            try:
                im = Image.open(io.BytesIO(data)).convert("RGB")
                images.append(im)
            except Exception:
                pass
    for p in doc.paragraphs:
        text.append(p.text)
    pages = [{"page_num": 1, "text": "\n".join(text), "images": images}]
    logger.info("Parsed DOCX into single concatenated page")
    return pages


