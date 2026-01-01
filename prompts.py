SYSTEM_PROMPT = (
    "You are a research assistant for a YouTube creator. "
    "Find diverse, reputable sources. Prefer primary sources when possible. "
    "Be concise and practical. Return output strictly in the required JSON schema."
)


USER_PROMPT_TEMPLATE = """\
Topic: {topic}
Model: {model}
Max items: {max_items}
Time window: {time_window}
Output style: {output_style}

Instructions:
- Find up to {max_items} high-quality, diverse sources (not all from the same domain).
- Summarize key takeaways and propose creator-friendly video angles.
- Include a credibility_score 1-10 (heuristic).
- If time window is provided, favor sources within that period.
- Keep results concise and practical for video ideation.
- Return JSON only, adhering to the provided schema fields.
"""


def build_user_prompt(
    topic: str,
    model: str,
    max_items: int,
    time_window: str,
    output_style: str,
) -> str:
    return USER_PROMPT_TEMPLATE.format(
        topic=topic.strip(),
        model=model,
        max_items=max_items,
        time_window=time_window or "none specified",
        output_style=output_style,
    )

