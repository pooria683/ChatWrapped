"""TF-IDF keyword / phrase extraction over user messages (pure stdlib).

Documents = individual user messages. Terms = unigrams and adjacent bigrams
after stopword removal. Scores are summed TF-IDF across the corpus, so terms
that are frequent in many messages but rare overall rise to the top.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'\-]*")

STOPWORDS = frozenset("""
a about above after again against all am an and any are aren't as at be because
been before being below between both but by can can't cannot could couldn't did
didn't do does doesn't doing don't down during each few for from further had
hadn't has hasn't have haven't having he he'd he'll he's her here here's hers
herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's
its itself let's me more most mustn't my myself no nor not of off on once only or
other ought our ours ourselves out over own same shan't she she'd she'll she's
should shouldn't so some such than that that's the their theirs them themselves
then there there's these they they'd they'll they're they've this those through to
too under until up very was wasn't we we'd we'll we're we've were weren't what
what's when when's where where's which while who who's whom why why's will with
won't would wouldn't you you'd you'll you're you've your yours yourself yourselves
also just like get got one two would could should may might make made way much many
still even back thing things way ways really dont im thats cant its hes thats
okay ok yes no well now new us me my mine yours their our ours himself herself
themselves anyone someone everyone noone nobody anything something everything
""".split())


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def extract_terms(text: str) -> Counter:
    """Unigrams + bigrams with stopwords and 1-2 char tokens removed."""
    raw = tokenize(text)
    words = [t for t in raw if t not in STOPWORDS and len(t) >= 3]
    terms = Counter(words)
    terms.update(f"{a} {b}" for a, b in zip(words, words[1:]))
    return terms


def tfidf_scores(docs: Iterable[str], max_terms: int = 20) -> list[tuple[str, float]]:
    """Return [(term, score)] sorted by descending summed TF-IDF."""
    tokenized = [extract_terms(d) for d in docs if d and d.strip()]
    n = len(tokenized)
    if n == 0:
        return []
    df: Counter = Counter()
    for terms in tokenized:
        df.update(terms.keys())
    scores: Counter = Counter()
    for terms in tokenized:
        total = sum(terms.values()) or 1
        for term, count in terms.items():
            tf = count / total
            idf = math.log((1 + n) / (1 + df[term])) + 1.0
            scores[term] += tf * idf
    return scores.most_common(max_terms)


def top_topics(messages: Iterable, n: int = 20) -> list[dict]:
    """Top-n topics over an iterable of messages (any role)."""
    docs = [m.text for m in messages if getattr(m, "text", "")]
    return [{"term": t, "score": round(s, 6)} for t, s in tfidf_scores(docs, n)]


def topics_by_month(messages: Iterable, per_month: int = 3, month_names: dict[int, str] | None = None) -> list[dict]:
    """Group messages by UTC month and compute top topics per month."""
    month_names = month_names or {
        1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
        7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
    }
    buckets: dict[int, list[str]] = {}
    for m in messages:
        ts = getattr(m, "created_at", None)
        text = getattr(m, "text", "")
        if ts is None or not text:
            continue
        buckets.setdefault(ts.month, []).append(text)
    out = []
    for month in sorted(buckets):
        tops = tfidf_scores(buckets[month], per_month)
        out.append({
            "month": month,
            "month_name": month_names.get(month, str(month)),
            "topics": [{"term": t, "score": round(s, 6)} for t, s in tops],
        })
    return out
