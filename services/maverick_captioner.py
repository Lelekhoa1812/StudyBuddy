import base64
import io
import os
from typing import Optional

import requests
from PIL import Image

from utils.logger import get_logger
try:
    from utils.api.rotator import APIKeyRotator  # available in full repo
except Exception:  # standalone fallback
    class APIKeyRotator:  # type: ignore
        def __init__(self, prefix: str = "NVIDIA_API_", max_slots: int = 5):
            self.keys = []
            for i in range(1, max_slots + 1):
                k = os.getenv(f"{prefix}{i}")
                if k:
                    self.keys.append(k)
            if not self.keys:
                single = os.getenv(prefix.rstrip("_"))
                if single:
                    self.keys.append(single)
            self._idx = 0

        def get_key(self) -> Optional[str]:
            if not self.keys:
                return None
            k = self.keys[self._idx % len(self.keys)]
            self._idx += 1
            return k


logger = get_logger("MAVERICK_CAPTIONER", __name__)


def _normalize_caption(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    # Remove common conversational/openers and meta phrases
    banned_prefixes = [
        "sure,", "sure.", "sure", "here is", "here are", "this image", "the image", "image shows",
        "the picture", "the photo", "the text describes", "the text describe", "it shows", "it depicts",
        "caption:", "description:", "output:", "result:", "answer:", "analysis:", "observation:",
    ]
    t_lower = t.lower()
    for p in banned_prefixes:
        if t_lower.startswith(p):
            t = t[len(p):].lstrip(" :-\u2014\u2013")
            t_lower = t.lower()

    # Strip surrounding quotes and markdown artifacts
    t = t.strip().strip('"').strip("'").strip()
    # Collapse whitespace
    t = " ".join(t.split())
    return t


class NvidiaMaverickCaptioner:
    """Caption images using NVIDIA Integrate API (meta/llama-4-maverick-17b-128e-instruct)."""

    def __init__(self, rotator: Optional[APIKeyRotator] = None, model: Optional[str] = None):
        self.rotator = rotator or APIKeyRotator(prefix="NVIDIA_API_", max_slots=5)
        self.model = model or os.getenv("NVIDIA_MAVERICK_MODEL", "meta/llama-4-maverick-17b-128e-instruct")
        self.invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"

    def _encode_image_jpeg_b64(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        # Convert to RGB to ensure JPEG-compatible
        image.convert("RGB").save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def caption_image(self, image: Image.Image) -> str:
        try:
            key = self.rotator.get_key()
            if not key:
                logger.warning("NVIDIA API key not available; skipping image caption.")
                return ""

            img_b64 = self._encode_image_jpeg_b64(image)

            # Strict, non-conversational system prompt
            system_prompt = (
                "You are an expert vision captioner. Produce a precise, information-dense caption of the image. "
                "Do not include conversational phrases, prefaces, meta commentary, or apologies. "
                "Avoid starting with phrases like 'The image/picture/photo shows' or 'Here is'. "
                "Write a single concise paragraph with concrete entities, text in the image, and notable details."
            )

            user_prompt = (
                "Caption this image at the finest level of detail. Include any visible text verbatim. "
                "Return only the caption text."
            )

            # Multimodal content format for NVIDIA Integrate API
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}"
                            }
                        },
                    ]
                },
            ]

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 512,
                "temperature": 0.2,
                "top_p": 0.9,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "stream": False,
            }

            headers = {
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            resp = requests.post(self.invoke_url, headers=headers, json=payload, timeout=60)
            if resp.status_code >= 400:
                logger.warning(f"Maverick caption API error {resp.status_code}: {resp.text[:200]}")
                return ""
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return _normalize_caption(text)
        except Exception as e:
            logger.warning(f"Maverick caption failed: {e}")
            return ""


