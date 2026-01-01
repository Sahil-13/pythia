from __future__ import annotations

import json
from typing import Any, Dict, Tuple

import pandas as pd
from pydantic import ValidationError

from schemas import ResearchItem, ResearchResponse


def parse_research_response(text: str) -> Tuple[ResearchResponse, Dict[str, Any]]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON: {exc}") from exc

    try:
        validated = ResearchResponse.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Response failed validation: {exc}") from exc

    return validated, raw


def items_to_dataframe(items: list[ResearchItem]) -> pd.DataFrame:
    rows = [item.model_dump() for item in items]
    if not rows:
        return pd.DataFrame(columns=["topic", "source_title", "url", "key_takeaway", "video_angle"])
    df = pd.DataFrame(rows)
    desired_order = [
        "topic",
        "source_title",
        "url",
        "source_type",
        "key_takeaway",
        "video_angle",
        "credibility_score",
        "notes",
        "citations",
    ]
    # Reorder while keeping any extras at the end
    cols = [c for c in desired_order if c in df.columns] + [c for c in df.columns if c not in desired_order]
    return df[cols]


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_json_bytes(raw: Dict[str, Any]) -> bytes:
    return json.dumps(raw, indent=2, ensure_ascii=False).encode("utf-8")


def brief_markdown(topic: str, summary: str, df: pd.DataFrame, model: str) -> str:
    table_md = _df_to_markdown(df) if not df.empty else "_No items returned_"
    return (
        f"# Research Brief: {topic}\n\n"
        f"- Model: {model}\n"
        f"- Items: {len(df)}\n\n"
        f"## Summary\n{summary}\n\n"
        f"## Sources & Angles\n{table_md}\n"
    )


def _df_to_markdown(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False)
    except ImportError:
        # Fallback if tabulate is not installed; not as pretty but avoids crash
        return df.to_string(index=False)

