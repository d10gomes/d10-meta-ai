import pytest
from app.agents.creative.service import CreativeService


def make_svc():
    svc = CreativeService.__new__(CreativeService)
    return svc


def test_winner_score():
    svc = make_svc()
    score = svc._compute_score(ctr=3.5, cpa=20.0, roas=5.0)
    assert score >= 70
    assert svc._tier(score) == "winner"


def test_loser_score():
    svc = make_svc()
    score = svc._compute_score(ctr=0.2, cpa=500.0, roas=0.1)
    assert score < 40
    assert svc._tier(score) == "loser"


def test_average_score():
    svc = make_svc()
    score = svc._compute_score(ctr=1.5, cpa=80.0, roas=2.0)
    assert 40 <= score < 70
    assert svc._tier(score) == "average"
