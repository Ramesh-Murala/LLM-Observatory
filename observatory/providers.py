"""Provider boundary shared by deterministic fixtures and an opt-in remote adapter."""

import os
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    usage_source: str


class Provider(Protocol):
    def complete(self, case: dict, variant: str) -> Completion: ...


class FixtureProvider:
    def complete(self, case: dict, variant: str) -> Completion:
        text = case["candidate"] if variant == "candidate" else case["baseline"]
        # Word counts are intentionally labelled estimates; they are not tokenizer counts.
        return Completion(text, len(case["prompt"].split()), len(text.split()), "word-estimate")


class CompatibleProvider:
    """Chat-completions adapter. Explicit configuration prevents accidental paid calls."""

    def __init__(self):
        self.base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        self.key = os.environ.get("LLM_API_KEY", "")
        if not self.base_url or not self.key:
            raise ValueError("Remote provider requires LLM_BASE_URL and LLM_API_KEY")

    def complete(self, case: dict, variant: str) -> Completion:
        model = os.environ.get(f"LLM_{variant.upper()}_MODEL")
        if not model:
            raise ValueError(f"Set LLM_{variant.upper()}_MODEL")
        with httpx.Client(timeout=45) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json={"model": model, "messages": [{"role": "user", "content": case["prompt"]}]},
            )
            response.raise_for_status()
            body = response.json()
        usage = body.get("usage", {})
        has_usage = all(
            type(usage.get(key)) is int and usage[key] >= 0
            for key in ("prompt_tokens", "completion_tokens")
        )
        return Completion(
            body["choices"][0]["message"]["content"],
            usage["prompt_tokens"] if has_usage else 0,
            usage["completion_tokens"] if has_usage else 0,
            "provider" if has_usage else "unavailable",
        )
