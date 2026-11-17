"""TF-IDF topic extraction tests."""

from __future__ import annotations

from chatwrapped.topics import STOPWORDS, extract_terms, tfidf_scores, topics_by_month


class M:
    def __init__(self, text, month=None):
        self.text = text
        self.created_at = None
        if month:
            from datetime import datetime, timezone
            self.created_at = datetime(2026, month, 15, tzinfo=timezone.utc)


def test_stopwords_removed():
    terms = extract_terms("The quick brown fox jumps over the lazy dog and the cat")
    keys = set(terms)
    assert "the" not in keys and "and" not in keys
    assert "quick" in keys and "fox" in keys


def test_bigrams_extracted():
    terms = extract_terms("machine learning models are great for machine learning")
    assert terms["machine learning"] >= 2
    assert terms["machine"] >= 2


def test_tfidf_ranks_distinctive_terms():
    docs = [
        "pasta pasta pasta pasta",          # concentrated in one doc -> high idf * tf
        "python code",
        "python review",
        "code review",
    ]
    scores = dict(tfidf_scores(docs, 10))
    assert "pasta" in scores and "python" in scores
    # 'pasta' is in 1/4 docs with tf=1 -> beats 'python' spread thin over 2/4 docs
    assert scores["pasta"] > scores["python"]


def test_tfidf_empty():
    assert tfidf_scores([]) == []
    assert tfidf_scores(["", "   "]) == []


def test_topics_by_month():
    msgs = [
        M("kyoto temples travel japan kyoto", month=1),
        M("kyoto japan travel shrine", month=1),
        M("python asyncio bug code", month=3),
        M("asyncio code python debug", month=3),
    ]
    out = topics_by_month(msgs, per_month=2)
    assert [o["month"] for o in out] == [1, 3]
    jan_terms = {t["term"] for t in out[0]["topics"]}
    mar_terms = {t["term"] for t in out[1]["topics"]}
    assert any("kyoto" in t or "japan" in t for t in jan_terms)
    assert any("asyncio" in t or "python" in t for t in mar_terms)


def test_stopword_list_sane():
    assert len(STOPWORDS) > 100
    assert "the" in STOPWORDS and "python" not in STOPWORDS
