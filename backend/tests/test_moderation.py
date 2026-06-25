from backend.moderation import is_clean


def test_clean_text_passes_including_tricky_real_names():
    # Real names that embed letters of profanity must NOT be flagged (the "Scunthorpe problem"),
    # and empty/whitespace/None is clean (required + length are enforced elsewhere).
    for ok in ["Quantum Cat", "Schrödinger's Bag", "Scunthorpe", "assassin", "Cockburn", "", "  ", None]:
        assert is_clean(ok) is True, ok


def test_profanity_blocked_including_leetspeak():
    for bad in ["sh1t", "f@ck this", "a$$hole"]:
        assert is_clean(bad) is False, bad
