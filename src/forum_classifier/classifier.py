from __future__ import annotations

import json
import logging
import re
import base64

import requests

from .models import Classification, Comment

logger = logging.getLogger(__name__)

DEFAULT_LLM_TIMEOUT = 600.0


SYSTEM_PROMPT = """You classify one forum comment about DIY audio/electronics.
Return JSON only with these keys:
category: one concise lowercase label. Use banter for non-technical comments.
For technical comments use the most specific component or concept, such as mechanism,
regulator, resistor, capacitor, DAC, transport, power-supply, clock, grounding,
measurement, or troubleshooting. Create another concise label if none fits.
summary: one sentence describing what the comment is about.
subjects: an array of up to five concise technical subjects (empty for banter).
confidence: high, medium, or low.
Do not infer facts that are not in the comment."""


class LocalClassifier:
    def __init__(self, base_url: str = "http://127.0.0.1:8080/v1", model: str = "local-model", timeout: float = DEFAULT_LLM_TIMEOUT):
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout

    def classify(self, comment: Comment) -> Classification:
        logger.info("Sending comment %s to LLM (%d characters)", comment.comment_id, len(comment.text))
        user_content: object = comment.text
        if comment.images:
            user_content = [{"type": "text", "text": comment.text}]
            user_content.extend({
                "type": "image_url",
                "image_url": {"url": f"data:{image.media_type};base64,{base64.b64encode(image.data).decode('ascii')}", "detail": "auto"},
            } for image in comment.images)
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        response = requests.post(self.endpoint, json=payload, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        data = json.loads(self._strip_fences(content))
        category = self._clean_label(data.get("category", "uncategorized"))
        subjects = tuple(self._clean_label(s) for s in data.get("subjects", []) if str(s).strip())
        logger.info("Classified comment %s as %s", comment.comment_id, category)
        return Classification(category, str(data.get("summary", "No summary provided")).strip(), subjects, str(data.get("confidence", "unknown")).lower())

    @staticmethod
    def _strip_fences(content: str) -> str:
        return re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)

    @staticmethod
    def _clean_label(value: object) -> str:
        label = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
        return label[:60] or "uncategorized"
