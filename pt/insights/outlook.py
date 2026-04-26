"""Generate per-asset outlook briefings via the LLM.

The prompt expects: a list of recent news items (title + summary + sentiment),
recent price action (last_close, 7d_change, 30d_change), and the user's
position context (qty, avg_cost, holding_period). The output is a structured
JSON object the UI can render directly.

We keep prompts in this module so they version with the code (refactor-safe).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

from pt.db import insights as _insights
from pt.db import news as _news
from pt.insights import llm

INSIGHT_TYPE = "asset_outlook"
DEFAULT_VALID_FOR_DAYS = 7
NEWS_LOOKBACK_DAYS = 14
NEWS_LIMIT = 12

SYSTEM_PROMPT = """\
You are a sober, numerate investment analyst writing personal-portfolio
briefings for a self-directed retail investor. You do NOT give buy/sell
advice — you summarise context: what happened, what to watch, what risks
matter for this specific holding right now.

Tone: concise, neutral, factual. Avoid hype, avoid disclaimers, avoid bullet
salads. Maximum 4 short paragraphs total.

Always respond with a single JSON object matching this shape exactly (no
extra keys, no prose around it):

{
  "headline": "<= 80 chars, one-line take",
  "summary": "<= 240 chars, plain prose",
  "narrative": "<= 1500 chars, 2-4 short paragraphs",
  "risks": ["...", "..."],          // 2-5 items, plain prose, no leading dashes
  "watch": ["...", "..."],          // 2-5 concrete things to monitor
  "sentiment": "bullish|neutral|cautious|bearish",
  "confidence": 0.0..1.0
}
"""


def generate_outlook(
    symbol: str,
    asset_type: str,
    *,
    qty: Decimal | None = None,
    avg_cost: Decimal | None = None,
    currency: str | None = None,
    last_close: Decimal | None = None,
    change_7d_pct: float | None = None,
    change_30d_pct: float | None = None,
    holding_period_days: int | None = None,
    model: str = llm.MODEL_SUMMARY,
    persist: bool = True,
) -> dict:
    """Build the prompt, call OpenRouter, persist the resulting insight.

    Returns the parsed JSON object plus the LLM raw response stamped onto
    `_meta` (model, tokens, latency_ms). When `persist=True`, the insight is
    written to asset_insights with a 7-day TTL.
    """
    news_items = _news.list_for_symbol(symbol, asset_type, limit=NEWS_LIMIT)
    avg_sent = _news.avg_sentiment(symbol, asset_type, lookback_days=NEWS_LOOKBACK_DAYS)

    user_prompt = _build_user_prompt(
        symbol=symbol, asset_type=asset_type,
        qty=qty, avg_cost=avg_cost, currency=currency,
        last_close=last_close,
        change_7d_pct=change_7d_pct, change_30d_pct=change_30d_pct,
        holding_period_days=holding_period_days,
        avg_sentiment=avg_sent,
        news_items=news_items,
    )

    parsed, resp = llm.chat_json(
        system=SYSTEM_PROMPT, user=user_prompt, model=model,
    )
    parsed["_meta"] = {
        "model": resp.model,
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "latency_ms": resp.latency_ms,
    }

    if persist:
        _insights.insert(
            symbol=symbol,
            asset_type=asset_type,
            insight_type=INSIGHT_TYPE,
            content=json.dumps(parsed, default=str),
            model=resp.model,
            valid_for=timedelta(days=DEFAULT_VALID_FOR_DAYS),
            metadata={
                "news_items_used": len(news_items),
                "avg_sentiment": float(avg_sent) if avg_sent is not None else None,
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
            },
        )
    return parsed


def _build_user_prompt(
    *,
    symbol: str,
    asset_type: str,
    qty: Decimal | None,
    avg_cost: Decimal | None,
    currency: str | None,
    last_close: Decimal | None,
    change_7d_pct: float | None,
    change_30d_pct: float | None,
    holding_period_days: int | None,
    avg_sentiment: Decimal | None,
    news_items: list[dict],
) -> str:
    lines = [
        f"Asset: {symbol} ({asset_type})",
        f"Generated at: {datetime.utcnow().isoformat(timespec='seconds')}Z",
        "",
        "Position context:",
    ]
    if qty is not None:
        lines.append(f"  - quantity held: {qty}")
    if avg_cost is not None and currency:
        lines.append(f"  - avg cost: {avg_cost} {currency}")
    if holding_period_days is not None:
        lines.append(f"  - first acquired: {holding_period_days} days ago")
    if last_close is not None and currency:
        lines.append(f"  - last close: {last_close} {currency}")
    if change_7d_pct is not None:
        lines.append(f"  - 7d change: {change_7d_pct:+.2f}%")
    if change_30d_pct is not None:
        lines.append(f"  - 30d change: {change_30d_pct:+.2f}%")
    if avg_sentiment is not None:
        lines.append(f"  - 14d avg news sentiment (-1..+1): {float(avg_sentiment):+.2f}")
    if not news_items:
        lines.append("")
        lines.append("Recent news: none in the database — inference must be cautious.")
    else:
        lines.append("")
        lines.append(f"Recent news ({len(news_items)} items, newest first):")
        for n in news_items:
            published = n.get("published_at")
            ts = published.strftime("%Y-%m-%d") if published else "?"
            sent = n.get("sentiment")
            sent_tag = f" [sent {float(sent):+.2f}]" if sent is not None else ""
            lines.append(f"  - {ts}{sent_tag} {n.get('title')!r}")
            summary = n.get("summary")
            if summary:
                lines.append(f"      {summary[:180]}")
    lines.append("")
    lines.append(
        "Produce the JSON object as specified. Be specific to THIS asset and "
        "this user's position; avoid generic platitudes."
    )
    return "\n".join(lines)


def parse_persisted_content(content: str) -> dict:
    """Decode an `asset_insights.content` row stored as JSON string."""
    return json.loads(content)
