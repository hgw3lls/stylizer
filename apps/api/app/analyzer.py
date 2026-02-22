import json
from pathlib import Path
from typing import Protocol
from urllib import error, request

from pydantic import ValidationError

from app.config import settings
from app.schemas import Constraints, PromptAnchors

STYLE_PACK_ANALYSIS_PROMPT = """
You are analyzing reference style images to build a style pack.
Return valid JSON only. Do not include markdown, comments, or prose.
The JSON object MUST match this exact shape with no extra keys:
{
  "constraints": {
    "palette": ["...optional strings..."],
    "materials": ["...optional strings..."],
    "line_rules": ["...strings..."],
    "composition_rules": ["...strings..."],
    "translation_rules": ["...strings..."],
    "forbidden": ["...strings..."]
  },
  "prompt_anchors": {
    "base_prompt": "...",
    "negative_prompt": "...",
    "variability_knobs": {
      "drift": 0.0,
      "density": 0.0,
      "abstraction": 0.0
    }
  }
}
Rules:
- JSON must be syntactically valid.
- All required keys must exist.
- variability_knobs values must be numbers in [0, 1].
- No extra keys at any level.
""".strip()


class StylePackAnalyzer(Protocol):
    def analyze(self, image_paths: list[str], validation_errors: str | None = None) -> tuple[Constraints, PromptAnchors]:
        ...


class OpenAIStylePackAnalyzer:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def analyze(self, image_paths: list[str], validation_errors: str | None = None) -> tuple[Constraints, PromptAnchors]:
        raw = self._call_openai(image_paths=image_paths, validation_errors=validation_errors)
        parsed = json.loads(raw)
        constraints = Constraints.model_validate(parsed["constraints"])
        prompt_anchors = PromptAnchors.model_validate(parsed["prompt_anchors"])
        return constraints, prompt_anchors

    def _call_openai(self, image_paths: list[str], validation_errors: str | None = None) -> str:
        image_lines = "\n".join(f"- {Path(path).resolve()}" for path in image_paths)
        retry_hint = ""
        if validation_errors:
            retry_hint = f"\nPrevious output failed validation. Fix these errors exactly:\n{validation_errors}\n"

        user_prompt = (
            "Analyze the style images listed below and return only the required JSON object.\n"
            f"Image paths:\n{image_lines}\n"
            "Use the image files as reference style sources."
            f"{retry_hint}"
        )

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": STYLE_PACK_ANALYSIS_PROMPT}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
        }
        req = request.Request(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI API error: {exc.code} {body}") from exc

        if "output_text" in data and isinstance(data["output_text"], str):
            return data["output_text"]

        output = data.get("output", [])
        if not output:
            raise RuntimeError("OpenAI response did not include output text")

        for item in output:
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    return text

        raise RuntimeError("OpenAI response could not be parsed into text")


def build_default_analyzer() -> StylePackAnalyzer:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for style pack analysis")
    return OpenAIStylePackAnalyzer(api_key=settings.openai_api_key, model=settings.openai_analysis_model)


def analyze_with_retry(analyzer: StylePackAnalyzer, image_paths: list[str]) -> tuple[Constraints, PromptAnchors]:
    try:
        return analyzer.analyze(image_paths=image_paths)
    except (json.JSONDecodeError, KeyError, ValidationError) as first_error:
        return analyzer.analyze(image_paths=image_paths, validation_errors=str(first_error))
