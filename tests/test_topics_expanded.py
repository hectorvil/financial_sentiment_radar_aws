"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

from financial_sentiment.topics import classify_topic


def test_moodys_mexico_rating_maps_to_sovereign_credit_rating():
    """Implements the `test_moodys_mexico_rating_maps_to_sovereign_credit_rating` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    text = "Moody’s recortó la calificación crediticia de México a Baa3"
    assert classify_topic(text) == "sovereign_credit_rating"


def test_banxico_rates_maps_to_monetary_policy():
    """Implements the `test_banxico_rates_maps_to_monetary_policy` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    text = "Banxico mantiene la tasa de interés por inflación persistente"
    assert classify_topic(text) == "monetary_policy"


def test_ia_does_not_match_inside_spanish_words():
    """Implements the `test_ia_does_not_match_inside_spanish_words` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    text = "Hacienda emitió comunicado sobre calificación soberana de México"
    assert classify_topic(text) == "sovereign_credit_rating"


def test_ai_chips_still_works_for_nvidia_gpu():
    """Implements the `test_ai_chips_still_works_for_nvidia_gpu` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    text = "Nvidia GPU demand rises as AI data center spending accelerates"
    assert classify_topic(text) == "ai_chips"
