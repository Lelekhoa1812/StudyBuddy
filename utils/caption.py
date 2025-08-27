# ────────────────────────────── utils/caption.py ──────────────────────────────
from typing import Optional
from PIL import Image
import logging
from .logger import get_logger

# Use transformers BLIP base (CPU friendly)
try:
    from transformers import BlipProcessor, BlipForConditionalGeneration
except Exception as e:
    BlipProcessor = None
    BlipForConditionalGeneration = None

logger = get_logger("CAPTION", __name__)


class BlipCaptioner:
    def __init__(self):
        self._ready = False
        self.processor = None
        self.model = None

    def _lazy_load(self):
        if self._ready:
            return
        if BlipProcessor is None or BlipForConditionalGeneration is None:
            logger.warning("transformers not available; image captions will be skipped.")
            self._ready = True
            return
        logger.info("Loading BLIP captioner (base)…")
        self.processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        self.model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        self._ready = True

    def caption_image(self, image: Image.Image) -> str:
        self._lazy_load()
        if self.processor is None or self.model is None:
            return ""
        inputs = self.processor(images=image, return_tensors="pt")
        out = self.model.generate(**inputs, max_new_tokens=40)
        return self.processor.decode(out[0], skip_special_tokens=True).strip()