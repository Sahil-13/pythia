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
Search mode: {search_mode_label}

Instructions:
- Find up to {max_items} high-quality, diverse sources (not all from the same domain).
- Summarize key takeaways and propose creator-friendly video angles.
- Include a credibility_score 1-10 (heuristic).
- If time window is provided, favor sources within that period.
- Keep results concise and practical for video ideation.
- Return JSON only, adhering to the provided schema fields.
{search_instructions}
"""


def _build_search_instructions(search_mode: str, time_window: str) -> tuple[str, str]:
    if search_mode == "reddit":
        label = "Reddit-only"
        instructions = """- Use only Reddit sources. Prefer high-signal subreddits such as:
  https://www.reddit.com/r/mythology/,
  https://www.reddit.com/r/philosophy/,
  https://www.reddit.com/r/UnresolvedMysteries/,
  https://www.reddit.com/r/AskHistorians/,
  https://www.reddit.com/r/Damnthatsinteresting/
  https://www.reddit.com/r/mystery/
  https://www.reddit.com/r/Phenomenology/
- Prioritize top or highly upvoted posts within the requested time window; if none provided, favor the last month.
- Return subreddit + post URLs in the url field; include subreddit names in source_title when helpful.
- Skip non-Reddit domains."""
    else:
        label = "Default / Web"
        instructions = "- Use diverse reputable web sources (news, papers, blogs, official docs) unless instructed otherwise."
    return label, instructions


def build_user_prompt(
    topic: str,
    model: str,
    max_items: int,
    time_window: str,
    output_style: str,
    search_mode: str = "default",
) -> str:
    search_mode_label, search_instructions = _build_search_instructions(search_mode, time_window)
    return USER_PROMPT_TEMPLATE.format(
        topic=topic.strip(),
        model=model,
        max_items=max_items,
        time_window=time_window or "none specified",
        output_style=output_style,
        search_mode_label=search_mode_label,
        search_instructions=search_instructions,
    )

