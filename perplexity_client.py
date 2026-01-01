from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

from schemas import RESEARCH_JSON_SCHEMA


class PerplexityClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.perplexity.ai",
    ) -> None:
        key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not key:
            raise ValueError("Perplexity API key not provided. Set PERPLEXITY_API_KEY.")
        self.client = OpenAI(api_key=key, base_url=base_url)

    def run_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        response_format: Dict[str, Any] = RESEARCH_JSON_SCHEMA,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        except RateLimitError as exc:
            raise RuntimeError("Perplexity rate limit hit. Try Sonar Pro or retry later.") from exc
        except APIConnectionError as exc:
            raise RuntimeError("Network error connecting to Perplexity.") from exc
        except APIError as exc:
            raise RuntimeError(f"Perplexity API error: {exc}") from exc

        if not resp.choices:
            raise RuntimeError("No choices returned from Perplexity.")
        message = resp.choices[0].message
        if not message or not message.content:
            raise RuntimeError("Empty response content from Perplexity.")
        return message.content

