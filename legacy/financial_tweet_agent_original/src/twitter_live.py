import os
import tweepy
from time import sleep

# ── Lista de cuentas financieras ──
handles = [
    "Bloomberg","Reuters","FT","WSJ","CNBC","CNNBusiness","BBCBusiness","APBusiness",
    "MarketWatch","YahooFinance","Forbes","TheEconomist","WSJmarkets","markets",
    "Benzinga","Stocktwits","BreakoutStocks","bespokeinvest","nytimesbusiness","IBDinvestors",
    "WSJDealJournal","TheStreet","SeekingAlpha","Investingcom","MorningstarInc",
    "Investopedia","barronsonline","MorganStanley","GoldmanSachs","BlackRock","stlouisfed",
    "FortuneMagazine","BusinessInsider","ElFinanciero_Mx","eleconomista","ExpansionMx",
    "Forbes_Mexico","ReutersLatam","BloombergLinea","Banxico","BMVMercados","larepublica_co",
    "valoreconomico","AmericaEconomia","Gestionpe","Ambitocom","Cronistacom","DFinanciero",
    "IMFNews"]


# ── autenticación ────────────────────────────────────────────────
client = tweepy.Client(
    bearer_token=os.getenv("TWITTER_BEARER"),
    wait_on_rate_limit=True,
)

# ── helpers ───────────────────────────────────────────────────────
def chunked_queries(handles_list, max_len=512) -> list[str]:
    chunks, cur = [], []
    for h in handles_list:
        test = cur + [h]
        q = "(" + " OR ".join(f"from:{x}" for x in test) + ") -is:retweet"
        if len(q) > max_len:
            chunks.append(cur)
            cur = [h]
        else:
            cur = test
    if cur:
        chunks.append(cur)
    return ["(" + " OR ".join(f"from:{h}" for h in c) + ") -is:retweet" for c in chunks]


def _safe_request(fun, *args, **kwargs):
    """Envuelve la llamada a la API para manejar rate-limits."""
    try:
        return fun(*args, **kwargs)
    except tweepy.TooManyRequests:
        sleep(15)
    except Exception as e:
        print(f"[Twitter error] {e}")
    return None

# ── búsqueda principal ───────────────────────────────────────────
def search(query: str | None = None, n: int = 30) -> list[dict]:
    tweets = []
    if query:
        resp = _safe_request(
            client.search_recent_tweets,
            query=query + " -is:retweet",
            tweet_fields=["id", "text", "created_at", "lang"],
            max_results=min(n, 100),
        )
        if not resp or resp.data is None:
            return []
        tweets = resp.data
    else:
        collected = []
        for q in chunked_queries(handles.copy()):
            resp = _safe_request(
                client.search_recent_tweets,
                query=q,
                tweet_fields=["id", "text", "created_at", "lang"],
                max_results=100,
            )
            if resp and resp.data:
                collected.extend(resp.data)
            if len(collected) >= n:
                break
        tweets = collected[:n]

    return [
        {"doc_id": str(t.id), "text": t.text, "created_at": t.created_at}
        for t in tweets
        if getattr(t, "lang", "en") == "en"
    ]
