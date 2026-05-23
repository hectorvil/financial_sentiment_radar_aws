from financial_sentiment.topics import classify_topic


def test_moodys_mexico_rating_maps_to_sovereign_credit_rating():
    text = "Moody’s recortó la calificación crediticia de México a Baa3"
    assert classify_topic(text) == "sovereign_credit_rating"


def test_banxico_rates_maps_to_monetary_policy():
    text = "Banxico mantiene la tasa de interés por inflación persistente"
    assert classify_topic(text) == "monetary_policy"


def test_ia_does_not_match_inside_spanish_words():
    text = "Hacienda emitió comunicado sobre calificación soberana de México"
    assert classify_topic(text) == "sovereign_credit_rating"


def test_ai_chips_still_works_for_nvidia_gpu():
    text = "Nvidia GPU demand rises as AI data center spending accelerates"
    assert classify_topic(text) == "ai_chips"
