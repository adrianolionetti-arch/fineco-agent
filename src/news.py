"""
Aggregatore news finanziarie da feed RSS gratuiti.
Nessuna API key richiesta.
"""
import feedparser
from datetime import datetime, timedelta, timezone
import re

# Feed RSS gratuiti di fonti affidabili
RSS_FEEDS = {
    "Reuters Markets": "https://www.reutersagency.com/feed/?best-topics=markets&post_type=best",
    "Yahoo Finance Top": "https://finance.yahoo.com/news/rssindex",
    "Il Sole 24 Ore Finanza": "https://www.ilsole24ore.com/rss/finanza.xml",
    "Investing.com News": "https://www.investing.com/rss/news.rss",
    "CNBC Top News": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "MarketWatch Top": "https://feeds.marketwatch.com/marketwatch/topstories/",
}

# Parole chiave per filtrare news rilevanti per il portafoglio
DEFAULT_KEYWORDS = [
    "fed", "federal reserve", "ecb", "bce", "inflation", "inflazione",
    "interest rate", "tassi", "recession", "recessione",
    "earnings", "trimestrale", "gdp", "pil",
]


def fetch_news(hours_back: int = 24, portfolio_tickers: list = None) -> list:
    """Scarica news dalle ultime N ore, filtrate per rilevanza."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    keywords = list(DEFAULT_KEYWORDS)
    if portfolio_tickers:
        # Aggiungi anche i nomi dei tuoi asset come keyword
        keywords.extend([t.lower() for t in portfolio_tickers])
        keywords.extend(["nvidia", "nvda"])  # esempi espansione nomi

    all_news = []
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:  # max 20 per fonte
                # parse timestamp
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                if published and published < cutoff:
                    continue

                title = entry.get("title", "").strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:300].strip()
                link = entry.get("link", "")

                # Check rilevanza
                text_lower = (title + " " + summary).lower()
                relevance = sum(1 for kw in keywords if kw.lower() in text_lower)

                all_news.append({
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": published.isoformat() if published else None,
                    "relevance_score": relevance,
                })
        except Exception as e:
            print(f"[WARN] Errore fetching {source_name}: {e}")

    # Ordina per rilevanza poi per data
    all_news.sort(
        key=lambda x: (x["relevance_score"], x["published"] or ""),
        reverse=True,
    )
    return all_news[:30]  # top 30


if __name__ == "__main__":
    news = fetch_news(hours_back=24, portfolio_tickers=["NVDA"])
    for n in news[:10]:
        print(f"[{n['relevance_score']}] {n['source']}: {n['title']}")
