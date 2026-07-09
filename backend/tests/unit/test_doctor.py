import pytest
from app.agents.doctor.service import DoctorService, THRESHOLDS
from app.domain.entities.diagnosis import IssueType


class MockMetric:
    def __init__(self, **kwargs):
        defaults = dict(ctr=2.0, cpa=50.0, cpm=10.0, roas=2.0, frequency=1.5,
                        impressions=5000, spend=100.0, conversions=2)
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class MockAd:
    meta_ad_id = "ad_123"


def make_svc():
    svc = DoctorService.__new__(DoctorService)
    return svc


def test_no_issues_on_healthy_ad():
    svc = make_svc()
    issues = svc._diagnose_ad(MockAd(), MockMetric(), avg_cpa=50.0, avg_cpm=10.0, tenant_id="t1")
    assert issues == []


def test_detects_low_ctr():
    svc = make_svc()
    issues = svc._diagnose_ad(MockAd(), MockMetric(ctr=0.3, impressions=2000), avg_cpa=50.0, avg_cpm=10.0, tenant_id="t1")
    types = [i.issue_type for i in issues]
    assert IssueType.LOW_CTR in types


def test_detects_no_conversions():
    svc = make_svc()
    issues = svc._diagnose_ad(MockAd(), MockMetric(spend=100.0, conversions=0, cpa=None), avg_cpa=50.0, avg_cpm=10.0, tenant_id="t1")
    types = [i.issue_type for i in issues]
    assert IssueType.NO_CONVERSIONS in types


def test_detects_high_frequency():
    svc = make_svc()
    issues = svc._diagnose_ad(MockAd(), MockMetric(frequency=4.5), avg_cpa=50.0, avg_cpm=10.0, tenant_id="t1")
    types = [i.issue_type for i in issues]
    assert IssueType.HIGH_FREQUENCY in types
