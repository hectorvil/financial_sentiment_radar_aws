from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AnchorGroup:
    name: str
    terms: tuple[str, ...]
    kind: str


ANCHOR_GROUPS: tuple[AnchorGroup, ...] = (
    # Rating agencies / sovereign credit
    AnchorGroup("moody", ("moody", "moodys", "moody's", "moody’s"), "rating_agency"),
    AnchorGroup("fitch", ("fitch",), "rating_agency"),
    AnchorGroup(
        "sp_rating",
        ("s&p", "standard poor", "standard & poor", "standard and poor"),
        "rating_agency",
    ),
    AnchorGroup(
        "rating_codes",
        (
            "baa3",
            "baa2",
            "bbb",
            "bb+",
            "bb-",
            "investment grade",
            "grado de inversion",
            "grado de inversión",
        ),
        "rating_code",
    ),
    AnchorGroup(
        "credit_rating_theme",
        (
            "credit rating",
            "sovereign rating",
            "calificacion crediticia",
            "calificación crediticia",
            "calificacion soberana",
            "calificación soberana",
            "nota soberana",
            "deuda soberana",
            "riesgo pais",
            "riesgo país",
        ),
        "theme",
    ),
    # Countries / macro geographies
    AnchorGroup("mexico", ("mexico", "méxico", "mexican", "mexicano", "mexicana"), "country"),
    AnchorGroup("colombia", ("colombia", "colombian", "colombiano", "colombiana"), "country"),
    AnchorGroup("brazil", ("brazil", "brasil", "brazilian", "brasileño", "brasileña"), "country"),
    AnchorGroup("argentina", ("argentina", "argentine", "argentino", "argentina"), "country"),
    AnchorGroup("chile", ("chile", "chilean", "chileno", "chilena"), "country"),
    AnchorGroup("peru", ("peru", "perú", "peruvian", "peruano", "peruana"), "country"),
    AnchorGroup("usa", ("usa", "u.s.", "united states", "estados unidos"), "country"),
    AnchorGroup("europe", ("europe", "europa", "eurozone", "zona euro"), "region"),
    AnchorGroup("china", ("china", "chinese"), "country"),
    # Central banks / macro
    AnchorGroup("banxico", ("banxico", "banco de mexico", "banco de méxico"), "central_bank"),
    AnchorGroup(
        "fed", ("fed", "federal reserve", "fomc", "jerome powell", "powell"), "central_bank"
    ),
    AnchorGroup(
        "ecb", ("ecb", "bce", "european central bank", "banco central europeo"), "central_bank"
    ),
    AnchorGroup(
        "banrep", ("banrep", "banco de la republica", "banco de la república"), "central_bank"
    ),
    AnchorGroup("bcra", ("bcra", "banco central de argentina"), "central_bank"),
    AnchorGroup(
        "monetary_policy",
        (
            "interest rate",
            "rate cut",
            "rate hike",
            "tasa de interes",
            "tasa de interés",
            "tasas",
            "inflacion",
            "inflación",
            "cpi",
            "policy rate",
            "politica monetaria",
            "política monetaria",
        ),
        "theme",
    ),
    # FX / rates
    AnchorGroup(
        "fx",
        (
            "fx",
            "forex",
            "currency",
            "exchange rate",
            "tipo de cambio",
            "usd/mxn",
            "usdmxn",
            "dollar",
            "dolar",
            "dólar",
            "peso",
            "euro",
            "yen",
        ),
        "theme",
    ),
    # Regulation / legal
    AnchorGroup(
        "antitrust_regulation",
        (
            "antitrust",
            "doj",
            "ftc",
            "sec",
            "regulation",
            "regulatory",
            "lawsuit",
            "probe",
            "investigation",
            "regulacion",
            "regulación",
            "demanda",
            "investigacion",
            "investigación",
            "cofece",
        ),
        "theme",
    ),
    # Geopolitical / commodities
    AnchorGroup(
        "geopolitical",
        (
            "geopolitical",
            "geopolitics",
            "war",
            "conflict",
            "tariff",
            "tariffs",
            "trade war",
            "middle east",
            "iran",
            "china",
            "russia",
            "ukraine",
            "guerra",
            "conflicto",
            "arancel",
            "aranceles",
        ),
        "theme",
    ),
    AnchorGroup(
        "energy",
        (
            "oil",
            "crude",
            "brent",
            "wti",
            "opec",
            "gas",
            "energy",
            "petroleo",
            "petróleo",
            "crudo",
            "energia",
            "energía",
        ),
        "theme",
    ),
    # Earnings / analyst
    AnchorGroup(
        "earnings_theme",
        (
            "earnings",
            "revenue",
            "profit",
            "eps",
            "guidance",
            "results",
            "sales",
            "margin",
            "margins",
            "resultados",
            "ingresos",
            "ventas",
            "utilidad",
            "guia",
            "guía",
        ),
        "theme",
    ),
    AnchorGroup(
        "analyst_theme",
        (
            "price target",
            "analyst",
            "upgrade",
            "downgrade",
            "buy rating",
            "sell rating",
            "overweight",
            "underweight",
            "precio objetivo",
            "recomendacion",
            "recomendación",
        ),
        "theme",
    ),
    # Companies / tickers
    AnchorGroup("google", ("google", "alphabet", "googl", "$googl"), "company"),
    AnchorGroup("tesla", ("tesla", "tsla", "$tsla", "elon musk"), "company"),
    AnchorGroup("nvidia", ("nvidia", "nvda", "$nvda"), "company"),
    AnchorGroup("microsoft", ("microsoft", "msft", "$msft"), "company"),
    AnchorGroup("apple", ("apple", "aapl", "$aapl", "iphone"), "company"),
    AnchorGroup("amazon", ("amazon", "amzn", "$amzn", "aws"), "company"),
    AnchorGroup("meta", ("meta", "facebook", "instagram", "$meta"), "company"),
    AnchorGroup("jpmorgan", ("jpm", "jpmorgan", "jp morgan", "$jpm"), "company"),
    AnchorGroup("bbva", ("bbva", "$bbva"), "company"),
    AnchorGroup("pltr", ("pltr", "palantir", "$pltr"), "company"),
    AnchorGroup("coin", ("coin", "coinbase", "$coin"), "company"),
    AnchorGroup("amd", ("amd", "$amd", "advanced micro devices"), "company"),
    AnchorGroup("avgo", ("avgo", "broadcom", "$avgo"), "company"),
    AnchorGroup("crm", ("crm", "salesforce", "$crm"), "company"),
    AnchorGroup("uber", ("uber", "$uber"), "company"),
    AnchorGroup("shop", ("shop", "shopify", "$shop"), "company"),
    AnchorGroup("visa", ("visa", "$v"), "company"),
    AnchorGroup("mastercard", ("mastercard", "$ma"), "company"),
    AnchorGroup("exxon", ("exxon", "xom", "$xom"), "company"),
    AnchorGroup("chevron", ("chevron", "cvx", "$cvx"), "company"),
    AnchorGroup("eli_lilly", ("lilly", "eli lilly", "lly", "$lly"), "company"),
    AnchorGroup("novo", ("novo nordisk", "nvo", "$nvo", "ozempic", "wegovy"), "company"),
    AnchorGroup("tsmc", ("tsmc", "taiwan semiconductor", "tsm", "$tsm"), "company"),
    AnchorGroup("costco", ("costco", "cost", "$cost"), "company"),
)


RATING_CONTEXT_IMPLIED_GROUP = AnchorGroup(
    "implied_credit_rating_context",
    (
        "rating",
        "credit rating",
        "sovereign rating",
        "calificacion",
        "calificación",
        "calificacion crediticia",
        "calificación crediticia",
        "calificacion soberana",
        "calificación soberana",
        "nota soberana",
        "deuda soberana",
        "grado de inversion",
        "grado de inversión",
        "downgrade",
        "upgrade",
        "recorta",
        "recortó",
        "rebaja",
        "rebajó",
        "baja calificacion",
        "baja calificación",
        "baa3",
        "baa2",
        "bbb",
    ),
    "theme",
)


def _augment_implied_credit_rating_context(groups: list[AnchorGroup]) -> list[AnchorGroup]:
    """Add rating context when user combines a rating agency with an entity.

    Example:
    Mexico Moody
    should mean:
    Mexico + Moody + rating/downgrade/calificación context

    This avoids returning generic Mexico macro tweets that only satisfy country terms.
    """
    if any(group.name == RATING_CONTEXT_IMPLIED_GROUP.name for group in groups):
        return groups

    has_rating_agency = any(group.kind == "rating_agency" for group in groups)
    has_entity = any(
        group.kind in {"country", "region", "company", "central_bank", "rating_code"}
        for group in groups
    )
    has_rating_context = any(
        group.name in {"credit_rating_theme", "rating_codes"} for group in groups
    )

    if has_rating_agency and has_entity and not has_rating_context:
        return [*groups, RATING_CONTEXT_IMPLIED_GROUP]

    return groups


GENERIC_ONLY_KINDS = {"theme"}
ENTITY_KINDS = {"company", "country", "central_bank", "rating_agency", "rating_code", "region"}


def _strip_accents(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(char)
    )


def _normalize(text: str) -> str:
    text = _strip_accents(str(text).lower())
    text = text.replace("+", " ")
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9$]+", _normalize(text)))


def _term_matches_text(term: str, normalized_text: str, token_set: set[str]) -> bool:
    term_norm = _normalize(term)

    if not term_norm:
        return False

    # Tickers and very short terms must be token matches, not substring matches.
    if term_norm.startswith("$"):
        return term_norm in token_set

    if len(term_norm) <= 3 and " " not in term_norm and "/" not in term_norm:
        return term_norm in token_set

    return term_norm in normalized_text


def _matched_groups(text: str) -> list[AnchorGroup]:
    normalized = _normalize(text)
    token_set = _tokens(text)
    matches: list[AnchorGroup] = []

    for group in ANCHOR_GROUPS:
        if any(_term_matches_text(term, normalized, token_set) for term in group.terms):
            matches.append(group)

    return matches


def extract_query_anchor_groups(user_query: str) -> list[str]:
    """Return matched anchor group names for debugging/testing."""
    return [group.name for group in _matched_groups(user_query)]


def _required_group_count(groups: list[AnchorGroup]) -> int:
    """Decide how strict the anchor filter should be.

    When a rating agency is combined with a concrete entity, require the entity,
    agency and rating context. This keeps results precise without expensive broad search.
    """
    if not groups:
        return 0

    groups = _augment_implied_credit_rating_context(groups)

    has_implied_rating = any(group.name == "implied_credit_rating_context" for group in groups)
    has_rating_agency = any(group.kind == "rating_agency" for group in groups)
    has_entity = any(group.kind in ENTITY_KINDS for group in groups)

    if has_rating_agency and has_entity and has_implied_rating:
        return 3

    entity_count = sum(group.kind in ENTITY_KINDS for group in groups)

    if len(groups) >= 2 and entity_count >= 1:
        return 2

    return 1


def _row_match_count(text: str, query_groups: list[AnchorGroup]) -> int:
    normalized = _normalize(text)
    token_set = _tokens(text)
    count = 0

    for group in query_groups:
        if any(_term_matches_text(term, normalized, token_set) for term in group.terms):
            count += 1

    return count


def filter_candidates_by_query_anchors(
    df: pd.DataFrame,
    user_query: str,
) -> tuple[pd.DataFrame, str | None]:
    """Filter candidates to preserve strong entities from the user query.

    General rule:
    if the user gives strong anchors, candidates must preserve enough of them.
    For rating-agency queries, also require rating/downgrade/calificación context.
    """
    if df.empty or "text" not in df.columns:
        return df, None

    groups = _matched_groups(user_query)
    groups = _augment_implied_credit_rating_context(groups)
    required = _required_group_count(groups)

    if required == 0:
        return df, None

    out = df.copy()
    match_counts = (
        out["text"].fillna("").astype(str).map(lambda text: _row_match_count(text, groups))
    )
    out["anchor_match_count"] = match_counts

    filtered = out[out["anchor_match_count"] >= required].copy()

    group_names = ", ".join(group.name for group in groups)

    if filtered.empty:
        return filtered, (
            "La búsqueda encontró candidatos, pero ninguno conservó suficientes "
            f"anclas de la consulta ({group_names}). Prueba con más resultados, "
            "recency o una frase menos restrictiva."
        )

    return filtered.reset_index(drop=True), (
        f"Se preservaron candidatos con al menos {required} anclas de consulta: {group_names}."
    )


def _quote_x_term(term: str) -> str:
    term = str(term).strip()
    if not term:
        return ""
    if " " in term or "&" in term or "'" in term or "’" in term:
        escaped = term.replace('"', "")
        return f'"{escaped}"'
    return term


def _group_query_terms(group: AnchorGroup, *, max_terms: int = 6) -> list[str]:
    """Return compact query terms for one anchor group."""
    terms = []
    for term in group.terms:
        q = _quote_x_term(term)
        if q and q not in terms:
            terms.append(q)
        if len(terms) >= max_terms:
            break
    return terms


def build_precise_anchor_query(user_query: str, *, language: str = "auto") -> str | None:
    """Build a precise, low-cost X query from strong user-query anchors.

    Strong-entity queries should preserve user intent instead of becoming broad macro searches.
    Examples:
    - Mexico Moody -> Mexico + Moody + rating context
    - Google antitrust DOJ -> Google + antitrust/regulation
    - Banxico tasa inflación -> Banxico + monetary policy
    """
    raw = str(user_query or "").strip()

    # Avoid applying another precision layer to already-expanded boolean queries.
    if " OR " in raw or "(" in raw or ")" in raw:
        return None

    groups = _matched_groups(raw)
    groups = _augment_implied_credit_rating_context(groups)

    if not groups:
        return None

    selected: list[AnchorGroup] = []

    country_groups = [group for group in groups if group.kind in {"country", "region"}]
    selected.extend(country_groups[:1])

    entity_groups = [
        group
        for group in groups
        if group.kind in {"company", "central_bank", "rating_agency"} and group not in selected
    ]
    selected.extend(entity_groups[:2])

    rating_code_groups = [
        group for group in groups if group.kind == "rating_code" and group not in selected
    ]
    selected.extend(rating_code_groups[:1])

    theme_groups = [group for group in groups if group.kind == "theme" and group not in selected]
    selected.extend(theme_groups[:2])

    if len(selected) < 2:
        return None

    clauses = []
    for group in selected[:5]:
        terms = _group_query_terms(group, max_terms=8)
        if terms:
            clauses.append("(" + " OR ".join(terms) + ")")

    if len(clauses) < 2:
        return None

    query = " ".join(clauses)

    if language in {"es", "en"}:
        query += f" lang:{language}"

    query += ' -is:retweet -giveaway -airdrop -"free crypto"'

    if len(query) > 500:
        query = query[:500].rsplit(" ", 1)[0]

    return query
