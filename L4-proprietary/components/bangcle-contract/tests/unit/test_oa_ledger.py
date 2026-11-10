"""services.oa.ledger 纯函数单测（无网络）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from services.oa.ledger import extract_billids, parse_search_results

def test_extract_billids_href():
    assert extract_billids('<a href="https://oa.bangcle.com/spa/cube/index.html#/main/cube/card?type=0&modeId=112&billid=15134">X</a>') == ['15134']

def test_extract_billids_onclick():
    assert extract_billids("onclick='openCard(15134)'") == ['15134']

def test_extract_billids_dedup():
    assert extract_billids("billid=1 billid=1 billid=2") == ['1', '2']

def test_extract_billids_empty():
    assert extract_billids("no billid here") == []

def test_parse_search_results():
    html = ('<a href="/card?billid=15134" onclick="openCard(15134)">XSZS2609020659</a>'
            '<a href="/card?billid=15135">XSZS2609020660</a>')
    rows = parse_search_results(html)
    assert len(rows) == 2
    assert rows[0]["contract_no"] == "XSZS2609020659"
    assert rows[0]["billid"] == "15134"
    assert rows[1]["billid"] == "15135"

def test_parse_search_results_no_hits():
    assert parse_search_results("<html>nothing</html>") == []
