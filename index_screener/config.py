"""Static universe of global stock indices used as the screener's data source.

Tickers use Yahoo Finance symbology (source for price/history data).
INDEX_UNIVERSE is iterated over by the data collection step.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexMeta:
    ticker: str    # Yahoo Finance symbol
    name: str      # Full index name
    country: str
    region: str    # North America / Europe / Asia-Pacific / South America
    currency: str  # Local currency the index is quoted in


# 20 liquid, large-cap indices spanning the major global regions.
INDEX_UNIVERSE: list[IndexMeta] = [
    IndexMeta("^GSPC", "S&P 500", "United States", "North America", "USD"),
    IndexMeta("^NDX", "Nasdaq 100", "United States", "North America", "USD"),
    IndexMeta("^DJI", "Dow Jones Industrial Average", "United States", "North America", "USD"),
    IndexMeta("^GSPTSE", "S&P/TSX Composite", "Canada", "North America", "CAD"),
    IndexMeta("^MXX", "IPC Mexico", "Mexico", "North America", "MXN"),
    IndexMeta("^FTSE", "FTSE 100", "United Kingdom", "Europe", "GBP"),
    IndexMeta("^GDAXI", "DAX", "Germany", "Europe", "EUR"),
    IndexMeta("^FCHI", "CAC 40", "France", "Europe", "EUR"),
    IndexMeta("^STOXX50E", "Euro Stoxx 50", "Eurozone", "Europe", "EUR"),
    IndexMeta("^IBEX", "IBEX 35", "Spain", "Europe", "EUR"),
    IndexMeta("^SSMI", "Swiss Market Index", "Switzerland", "Europe", "CHF"),
    IndexMeta("^N225", "Nikkei 225", "Japan", "Asia-Pacific", "JPY"),
    IndexMeta("^HSI", "Hang Seng Index", "Hong Kong", "Asia-Pacific", "HKD"),
    IndexMeta("000001.SS", "Shanghai Composite", "China", "Asia-Pacific", "CNY"),
    IndexMeta("000300.SS", "CSI 300", "China", "Asia-Pacific", "CNY"),
    IndexMeta("^KS11", "KOSPI Composite", "South Korea", "Asia-Pacific", "KRW"),
    IndexMeta("^NSEI", "Nifty 50", "India", "Asia-Pacific", "INR"),
    IndexMeta("^AXJO", "S&P/ASX 200", "Australia", "Asia-Pacific", "AUD"),
    IndexMeta("^TWII", "Taiwan Weighted", "Taiwan", "Asia-Pacific", "TWD"),
    IndexMeta("^BVSP", "Bovespa", "Brazil", "South America", "BRL"),
]
