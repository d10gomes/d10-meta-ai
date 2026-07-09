"""Doctor Agent — diagnoses CTR baixo, CPA alto, frequência alta, etc."""
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import AdMetric, Ad, AdSet, Campaign
from app.domain.entities.diagnosis import Diagnosis, IssueType, IssueSeverity
from app.domain.events.base import DomainEvent, EventTypes
from app.domain.events.bus import publish
from app.infrastructure.repositories.campaign_repository import CampaignRepository
from app.infrastructure.repositories.diagnosis_repository import DiagnosisRepository
from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository

# Thresholds (configurable per tenant in the future)
THRESHOLDS = {
    "ctr_low": 1.0,          # < 1% CTR
    "cpa_high_multiplier": 2.0,  # CPA > 2x account average
    "frequency_high": 3.5,   # frequency > 3.5
    "roas_low": 1.0,          # ROAS < 1 (spending more than earning)
    "no_conversions_days": 3, # 0 conversions after 3+ days spend
    "cpm_high_multiplier": 1.8,
}


class DoctorService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._account_repo = MetaAccountRepository(session)
        self._campaign_repo = CampaignRepository(session)
        self._diagnosis_repo = DiagnosisRepository(session)

    async def run(self, tenant_id: str):
        accounts = await self._account_repo.get_by_tenant(tenant_id)
        diagnoses: List[Diagnosis] = []

        for account in accounts:
            rows = await self._campaign_repo.get_ads_with_metrics(str(account.id))
            avg_cpa = self._compute_avg_cpa(rows)
            avg_cpm = self._compute_avg_cpm(rows)

            for ad, metric, adset, campaign in rows:
                if metric is None:
                    continue
                found = self._diagnose_ad(ad, metric, avg_cpa, avg_cpm, tenant_id)
                diagnoses.extend(found)

        for d in diagnoses:
            await self._diagnosis_repo.save_diagnosis({
                "tenant_id": d.tenant_id,
                "entity_type": d.entity_type,
                "entity_id": d.entity_id,
                "issue_type": d.issue_type.value,
                "severity": d.severity.value,
                "details": d.details,
            })
            await publish(DomainEvent(
                event_type=EventTypes.DIAGNOSIS_CREATED,
                tenant_id=tenant_id,
                payload={"issue_type": d.issue_type.value, "entity_id": d.entity_id},
            ))

        logger.info("doctor.done", tenant_id=tenant_id, diagnoses=len(diagnoses))
        return diagnoses

    def _diagnose_ad(self, ad, metric: AdMetric, avg_cpa: float, avg_cpm: float, tenant_id: str) -> List[Diagnosis]:
        issues = []
        entity_id = ad.meta_ad_id

        if metric.ctr is not None and metric.ctr < THRESHOLDS["ctr_low"] and metric.impressions > 1000:
            issues.append(Diagnosis(
                tenant_id=tenant_id,
                entity_type="ad",
                entity_id=entity_id,
                issue_type=IssueType.LOW_CTR,
                severity=IssueSeverity.HIGH if metric.ctr < 0.5 else IssueSeverity.MEDIUM,
                details={"ctr": metric.ctr, "threshold": THRESHOLDS["ctr_low"]},
            ))

        if avg_cpa > 0 and metric.cpa is not None and metric.cpa > avg_cpa * THRESHOLDS["cpa_high_multiplier"]:
            issues.append(Diagnosis(
                tenant_id=tenant_id,
                entity_type="ad",
                entity_id=entity_id,
                issue_type=IssueType.HIGH_CPA,
                severity=IssueSeverity.HIGH,
                details={"cpa": metric.cpa, "avg_cpa": avg_cpa},
            ))

        if metric.frequency is not None and metric.frequency > THRESHOLDS["frequency_high"]:
            issues.append(Diagnosis(
                tenant_id=tenant_id,
                entity_type="ad",
                entity_id=entity_id,
                issue_type=IssueType.HIGH_FREQUENCY,
                severity=IssueSeverity.CRITICAL if metric.frequency > 5 else IssueSeverity.HIGH,
                details={"frequency": metric.frequency, "threshold": THRESHOLDS["frequency_high"]},
            ))

        if metric.spend > 50 and metric.conversions == 0:
            issues.append(Diagnosis(
                tenant_id=tenant_id,
                entity_type="ad",
                entity_id=entity_id,
                issue_type=IssueType.NO_CONVERSIONS,
                severity=IssueSeverity.CRITICAL,
                details={"spend": metric.spend, "conversions": 0},
            ))

        if metric.roas is not None and metric.roas < THRESHOLDS["roas_low"] and metric.spend > 20:
            issues.append(Diagnosis(
                tenant_id=tenant_id,
                entity_type="ad",
                entity_id=entity_id,
                issue_type=IssueType.LOW_ROAS,
                severity=IssueSeverity.HIGH,
                details={"roas": metric.roas, "threshold": THRESHOLDS["roas_low"]},
            ))

        if avg_cpm > 0 and metric.cpm is not None and metric.cpm > avg_cpm * THRESHOLDS["cpm_high_multiplier"]:
            issues.append(Diagnosis(
                tenant_id=tenant_id,
                entity_type="ad",
                entity_id=entity_id,
                issue_type=IssueType.HIGH_CPM,
                severity=IssueSeverity.MEDIUM,
                details={"cpm": metric.cpm, "avg_cpm": avg_cpm},
            ))

        return issues

    def _compute_avg_cpa(self, rows) -> float:
        cpas = [m.cpa for _, m, _, _ in rows if m and m.cpa and m.cpa > 0]
        return sum(cpas) / len(cpas) if cpas else 0.0

    def _compute_avg_cpm(self, rows) -> float:
        cpms = [m.cpm for _, m, _, _ in rows if m and m.cpm and m.cpm > 0]
        return sum(cpms) / len(cpms) if cpms else 0.0
