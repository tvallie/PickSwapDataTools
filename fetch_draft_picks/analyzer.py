"""analyzer.py — AI conflict analysis and model selection."""

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
