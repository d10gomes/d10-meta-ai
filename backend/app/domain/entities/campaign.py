from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class CampaignMetrics:
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    conversions: int = 0
    revenue: float = 0.0
    reach: int = 0
    ctr: float = 0.0
    cpc: float = 0.0
    cpm: float = 0.0
    cpa: float = 0.0
    roas: float = 0.0
    frequency: float = 0.0

    @classmethod
    def compute(cls, impressions: int, clicks: int, spend: float,
                conversions: int, revenue: float, reach: int) -> "CampaignMetrics":
        ctr = (clicks / impressions * 100) if impressions else 0.0
        cpc = (spend / clicks) if clicks else 0.0
        cpm = (spend / impressions * 1000) if impressions else 0.0
        cpa = (spend / conversions) if conversions else 0.0
        roas = (revenue / spend) if spend else 0.0
        frequency = (impressions / reach) if reach else 0.0
        return cls(
            impressions=impressions, clicks=clicks, spend=spend,
            conversions=conversions, revenue=revenue, reach=reach,
            ctr=ctr, cpc=cpc, cpm=cpm, cpa=cpa, roas=roas, frequency=frequency,
        )


@dataclass
class Ad:
    meta_ad_id: str
    name: str
    status: str
    creative_id: Optional[str] = None
    creative_type: Optional[str] = None
    metrics: Optional[CampaignMetrics] = None


@dataclass
class AdSet:
    meta_adset_id: str
    name: str
    status: str
    daily_budget: Optional[float] = None
    ads: List[Ad] = field(default_factory=list)
    metrics: Optional[CampaignMetrics] = None


@dataclass
class Campaign:
    meta_campaign_id: str
    name: str
    status: str
    objective: Optional[str] = None
    daily_budget: Optional[float] = None
    lifetime_budget: Optional[float] = None
    adsets: List[AdSet] = field(default_factory=list)
    metrics: Optional[CampaignMetrics] = None
