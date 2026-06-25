"""Profanity guard for user-entered display text.

The player name (and the handle slugged from it) is shown on the public booth TV, the
leaderboard, and phone profiles — so a profane name would reach the big screen. This rejects it
at sign-up. better-profanity matches at the word level with leetspeak handling, so it catches
``sh1t`` / ``f@ck`` while leaving real names like ``Scunthorpe`` / ``Cockburn`` alone. The
operator dashboard can still hide anything that slips through.
"""

from __future__ import annotations

from better_profanity import profanity

# Load the bundled English word list once at import; the check is then in-memory.
profanity.load_censor_words()


def is_clean(text: str | None) -> bool:
    """True when the text carries no profanity. Empty/whitespace is clean (required/length are
    enforced by other validators); a single profane token anywhere makes the whole string unclean."""
    if not text or not text.strip():
        return True
    return not profanity.contains_profanity(text)
