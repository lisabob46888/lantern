"""Offline unit tests: id normalization, source-router fallback, validation gate, ingest dedupe."""
import os
import tempfile

os.environ["LANTERN_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app.services.securities import normalize  # noqa: E402
from app.sources.router import Provider, route  # noqa: E402


def test_normalize_spellings():
    assert normalize("600519") == "CN:600519"
    assert normalize("SH600519") == "CN:600519"
    assert normalize("600519.SS") == "CN:600519"
    assert normalize("0700.HK") == "HK:00700"
    assert normalize("00700") == "HK:00700"
    assert normalize("nvda") == "US:NVDA"
    assert normalize("IX:US:SPX") == "IX:US:SPX"
    assert normalize("") is None


def test_router_falls_through_errors_and_empties():
    def boom(_):
        raise RuntimeError("upstream down")
    res = route([Provider("t.boom", boom), Provider("t.empty", lambda _: []), Provider("t.ok", lambda x: [x])], 7)
    assert res.data == [7] and res.source == "t.ok"
    assert any("t.boom" in e for e in res.errors) and any("t.empty: empty" in e for e in res.errors)


def test_router_validation_gate_rejects_implausible_answers():
    res = route([Provider("t.bad", lambda: [{"c": -1}]), Provider("t.good", lambda: [{"c": 10}])],
                validate=lambda rows: all(r["c"] > 0 for r in rows))
    assert res.source == "t.good"


def test_router_all_fail_returns_empty_not_placeholder():
    res = route([Provider("t.none", lambda: None)])
    assert res.data is None and res.source is None and not res.ok


def test_ingest_dedupes_same_headline_across_sources():
    from app.pipeline.ingest import ingest
    from app.store import db
    now = db.now_ms()
    ev = {"source": "a", "source_id": "1", "kind": "news", "published_at": now, "title": "Fed holds rates steady",
          "body": "", "markets": ["US"], "symbols": []}
    assert ingest([ev], publish=False) == 1
    assert ingest([{**ev, "source": "b", "source_id": "9", "title": "Fed holds rates steady."}], publish=False) == 0
    assert ingest([ev], publish=False) == 0


def test_model_ticker_parsing():
    from app.enrich.worker import _sec_id
    assert _sec_id({"symbol": "688256.SH", "market": "CN"}) == "CN:688256"
    assert _sec_id({"symbol": "HK.0981", "market": "HK"}) == "HK:00981"
    assert _sec_id({"symbol": "NVDA.O", "market": "US"}) == "US:NVDA"
    assert _sec_id({"symbol": "abc", "market": "CN"}) is None
    assert _sec_id({"symbol": "NVDA", "market": "XX"}) is None


def test_name_check_rejects_wrong_ticker():
    from app.enrich.worker import name_matches
    assert name_matches("SMIC (中芯国际)", {"name": "", "nameZh": "中芯国际"})
    assert name_matches("NVIDIA", {"name": "Nvidia Corporation", "nameZh": "英伟达"})
    assert name_matches("Taiwan Semiconductor", {"name": "Taiwan Semiconductor Manufacturing", "nameZh": "台积电"})
    assert not name_matches("Hua Hong Semiconductor (华虹半导体)", {"name": "", "nameZh": "中石化冠德"})
