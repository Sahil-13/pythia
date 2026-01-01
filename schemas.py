from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# JSON schema used with the OpenAI-compatible response_format parameter
RESEARCH_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "research_output",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "source_title": {"type": "string"},
                            "url": {"type": "string"},
                            "source_type": {"type": "string"},
                            "key_takeaway": {"type": "string"},
                            "video_angle": {"type": "string"},
                            "credibility_score": {"type": "number"},
                            "notes": {"type": "string"},
                            "citations": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "topic",
                            "source_title",
                            "url",
                            "source_type",
                            "key_takeaway",
                            "video_angle",
                            "credibility_score",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "items"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


class ResearchItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    source_title: str
    url: str
    source_type: str = Field(description="e.g., reddit / blog / paper / wiki / video / forum / other")
    key_takeaway: str
    video_angle: str = Field(description="Explainer / Hot Take / Mythbust / Story / Listicle / etc.")
    credibility_score: float
    notes: Optional[str] = None
    citations: Optional[List[str]] = None


class ResearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str
    items: List[ResearchItem]

