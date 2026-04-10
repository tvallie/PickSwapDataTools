"""analyzer.py — AI conflict analysis and model selection."""
import json
import anthropic

HAIKU   = "claude-haiku-4-5-20251001"
SONNET  = "claude-sonnet-4-6"
OPUS    = "claude-opus-4-6"


def select_model(
    conflicts: list[dict],
    high_stake_rounds: set[int],
) -> tuple[str | None, str]:
    """Choose the cheapest Claude model sufficient for the conflict complexity.

    Returns:
        (model_id, reason_string) — model_id is None if no AI call needed.
    """
    n = len(conflicts)

    if n == 0:
        return None, "no conflicts — skipping AI analysis"

    has_high_stakes = bool(high_stake_rounds & {1, 2})

    if n >= 10 or (n >= 5 and has_high_stakes):
        return OPUS, f"{n} conflicts, high complexity"
    if n >= 4 or has_high_stakes:
        return SONNET, f"{n} conflicts" + (", includes R1/R2" if has_high_stakes else "")
    return HAIKU, f"{n} simple conflict(s)"


# Prompt is kept minimal to reduce tokens — only conflict data + relevant news
_CURRENT_PROMPT = """\
You are an NFL draft pick ownership expert. Below are pick ownership conflicts \
between data sources, followed by recent news snippets.

Conflicts (JSON):
{conflicts_json}

News snippets:
{news_text}

For each conflict, identify which source is most likely correct and why. \
Reply ONLY with a JSON object keyed by overall pick number (as string), \
each value having keys: "summary" (one sentence), "confidence" ("high"/"medium"/"low"), \
"recommended_abbr" (the team abbreviation you believe is correct).
"""

_FUTURE_PROMPT = """\
You are an NFL draft pick trade expert. Below are conflicts in future traded pick \
ownership between data sources, followed by recent news snippets.

Conflicts (JSON):
{conflicts_json}

News snippets:
{news_text}

For each conflict, identify which source is most likely correct and why. \
Reply ONLY with a JSON object keyed by "YEAR_ROUND_ORIGABBR" (e.g. "2027_1_IND"), \
each value having keys: "summary" (one sentence), "confidence" ("high"/"medium"/"low"), \
"recommended_current_abbr".
"""


def analyze_conflicts(
    conflicts: list[dict],
    news_snippets: list[str],
    mode: str,  # "current" or "future"
) -> dict:
    """Send conflicts to Claude and return per-conflict analysis.

    Args:
        conflicts: output of diff_current_picks or diff_future_picks
        news_snippets: recent headlines/snippets from news sources
        mode: "current" or "future"

    Returns:
        Dict keyed by pick identifier → {summary, confidence, recommended_*}
    """
    model, reason = select_model(
        conflicts=conflicts,
        high_stake_rounds={c.get("round", 99) for c in conflicts},
    )
    if model is None:
        return {}

    print(f"\n  AI model selected: {model} ({reason})")

    prompt_template = _CURRENT_PROMPT if mode == "current" else _FUTURE_PROMPT
    prompt = prompt_template.format(
        conflicts_json=json.dumps(conflicts, indent=2),
        news_text="\n".join(f"- {s}" for s in news_snippets) or "None available.",
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  Warning: AI response was not valid JSON. Raw:\n{raw}")
        return {}
