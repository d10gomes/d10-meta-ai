from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.exceptions import MetaAPIError
from app.core.logging import logger
from app.db.models import User, Campaign, MetaAccount, AdSet, Ad, AdMetric, AgentAction
from app.db.session import get_db
from app.infrastructure.meta_api.client import MetaAdsClient
from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository

router = APIRouter()

# ── Objective metadata ─────────────────────────────────────────────────────────

# Maps simple wizard key → Meta API objective
OBJECTIVE_MAP: dict[str, str] = {
    "sales":       "OUTCOME_SALES",
    "traffic":     "OUTCOME_TRAFFIC",
    "leads":       "OUTCOME_LEADS",
    "awareness":   "OUTCOME_AWARENESS",
    "engagement":  "OUTCOME_ENGAGEMENT",
    "messages":    "OUTCOME_TRAFFIC",
}

# Meta API objective → optimization_goal for adset
OPTIMIZATION_MAP: dict[str, str] = {
    "OUTCOME_SALES":      "OFFSITE_CONVERSIONS",
    "OUTCOME_TRAFFIC":    "LINK_CLICKS",
    "OUTCOME_LEADS":      "LEAD_GENERATION",
    "OUTCOME_AWARENESS":  "REACH",
    "OUTCOME_ENGAGEMENT": "POST_ENGAGEMENT",
}

# Meta API objective → billing_event for adset
BILLING_MAP: dict[str, str] = {
    "OUTCOME_SALES":      "IMPRESSIONS",
    "OUTCOME_TRAFFIC":    "LINK_CLICKS",
    "OUTCOME_LEADS":      "IMPRESSIONS",
    "OUTCOME_AWARENESS":  "IMPRESSIONS",
    "OUTCOME_ENGAGEMENT": "IMPRESSIONS",
}

# Friendly labels for the wizard
OBJECTIVE_LABELS: dict[str, dict] = {
    "sales":      {"label": "Mais Vendas",         "icon": "🛒", "description": "Gerar compras ou conversões no seu site"},
    "traffic":    {"label": "Mais Visitas",         "icon": "👁️", "description": "Trazer pessoas para o seu site ou página"},
    "leads":      {"label": "Captar Contatos",      "icon": "📩", "description": "Coletar emails ou telefones de clientes em potencial"},
    "awareness":  {"label": "Ser Mais Conhecido",   "icon": "📢", "description": "Mostrar sua marca para o maior número de pessoas"},
    "engagement": {"label": "Mais Engajamento",     "icon": "❤️", "description": "Curtidas, comentários e compartilhamentos nos seus posts"},
    "messages":   {"label": "Mensagens",            "icon": "💬", "description": "Receber mensagens no WhatsApp ou Instagram Direct"},
}

CTA_MAP: dict[str, str] = {
    "Comprar agora":   "SHOP_NOW",
    "Saiba mais":      "LEARN_MORE",
    "Entre em contato": "CONTACT_US",
    "Cadastrar-se":    "SIGN_UP",
    "Inscrever-se":    "SUBSCRIBE",
    "Solicitar orçamento": "GET_QUOTE",
}

# ── Schemas ───────────────────────────────────────────────────────────────────

class CampaignOut(BaseModel):
    id: str
    meta_campaign_id: str
    name: str | None
    status: str | None
    objective: str | None
    daily_budget: float | None
    # 7-day metrics (None if no data yet)
    spend_7d: float | None = None
    conversions_7d: int | None = None
    roas_7d: float | None = None
    cpa_7d: float | None = None
    ctr_7d: float | None = None
    clicks_7d: int | None = None
    impressions_7d: int | None = None


class CampaignCreateRequest(BaseModel):
    account_id: str          # UUID of MetaAccount in our DB
    campaign_name: str
    objective: str           # wizard key: "sales", "traffic", etc.
    daily_budget_brl: float  # in BRL — we convert to centavos

    # Audience
    age_min: int = 18
    age_max: int = 65
    genders: List[str] = []  # ["men"] | ["women"] | [] means both
    countries: List[str] = ["BR"]

    # Ad (all optional — campaign+adset are created even without an ad)
    page_id: Optional[str] = None
    headline: Optional[str] = None
    body: Optional[str] = None
    link_url: Optional[str] = None
    cta_label: Optional[str] = "Saiba mais"
    image_hash: Optional[str] = None  # from /campaigns/upload-image

    @field_validator("campaign_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome da campanha é obrigatório")
        return v

    @field_validator("daily_budget_brl")
    @classmethod
    def budget_minimum(cls, v: float) -> float:
        if v < 6:
            raise ValueError("Orçamento mínimo é R$ 6,00 por dia")
        return v

    @field_validator("objective")
    @classmethod
    def valid_objective(cls, v: str) -> str:
        if v not in OBJECTIVE_MAP:
            raise ValueError(f"Objetivo inválido. Opções: {list(OBJECTIVE_MAP.keys())}")
        return v


class CreateCampaignResult(BaseModel):
    meta_campaign_id: str
    meta_adset_id: Optional[str] = None
    meta_ad_id: Optional[str] = None
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

ERROR_TRANSLATIONS: dict[str, str] = {
    "Invalid account id": "ID da conta de anúncios inválido",
    "Invalid parameter": "Parâmetro inválido enviado para o Meta",
    "Invalid image": "Imagem inválida. Use JPG ou PNG com pelo menos 600x314 px",
    "budget": "Orçamento muito baixo para este objetivo",
    "permission": "Sem permissão para criar anúncios nesta conta",
    "access_token": "Token de acesso expirado. Reconecte a conta",
    "Page": "Página do Facebook não encontrada ou sem permissão",
    "URL": "Link inválido. Certifique-se de que começa com https://",
}

def translate_meta_error(msg: str) -> str:
    msg_lower = msg.lower()
    for key, pt in ERROR_TRANSLATIONS.items():
        if key.lower() in msg_lower:
            return pt
    return f"Erro do Meta Ads: {msg}"


async def _get_account_client(
    account_id: str, tenant_id: str, db: AsyncSession
) -> tuple[MetaAccount, MetaAdsClient]:
    result = await db.execute(
        select(MetaAccount).where(
            MetaAccount.id == account_id,
            MetaAccount.tenant_id == tenant_id,
            MetaAccount.is_active == True,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta Meta não encontrada")
    client = MetaAdsClient(account.access_token, account.ad_account_id)
    return account, client


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[CampaignOut])
async def list_campaigns(
    account_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Campaign)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(MetaAccount.tenant_id == current_user.tenant_id)
    )
    if account_id:
        q = q.where(Campaign.meta_account_id == account_id)
    result = await db.execute(q.limit(500))
    campaigns = result.scalars().all()

    # Aggregate 7-day metrics per campaign
    since = datetime.utcnow() - timedelta(days=7)
    campaign_ids = [str(c.id) for c in campaigns]

    metrics_map: dict[str, dict] = {}
    if campaign_ids:
        metrics_q = (
            select(
                Campaign.id.label("campaign_id"),
                func.sum(AdMetric.spend).label("spend"),
                func.sum(AdMetric.conversions).label("conversions"),
                func.sum(AdMetric.revenue).label("revenue"),
                func.sum(AdMetric.clicks).label("clicks"),
                func.sum(AdMetric.impressions).label("impressions"),
                func.avg(AdMetric.ctr).label("ctr"),
            )
            .select_from(Campaign)
            .join(AdSet, AdSet.campaign_id == Campaign.id)
            .join(Ad, Ad.adset_id == AdSet.id)
            .join(AdMetric, and_(AdMetric.ad_id == Ad.id, AdMetric.date >= since))
            .where(Campaign.id.in_(campaign_ids))
            .group_by(Campaign.id)
        )
        metrics_result = await db.execute(metrics_q)
        for row in metrics_result.all():
            spend = float(row.spend or 0)
            revenue = float(row.revenue or 0)
            conversions = int(row.conversions or 0)
            metrics_map[str(row.campaign_id)] = {
                "spend_7d": round(spend, 2),
                "conversions_7d": conversions,
                "roas_7d": round(revenue / spend, 2) if spend > 0 else None,
                "cpa_7d": round(spend / conversions, 2) if conversions > 0 else None,
                "ctr_7d": round(float(row.ctr or 0), 2),
                "clicks_7d": int(row.clicks or 0),
                "impressions_7d": int(row.impressions or 0),
            }

    return [CampaignOut(
        id=str(c.id),
        meta_campaign_id=c.meta_campaign_id,
        name=c.name,
        status=c.status,
        objective=c.objective,
        daily_budget=c.daily_budget,
        **metrics_map.get(str(c.id), {}),
    ) for c in campaigns]


@router.put("/{campaign_id}/status")
async def update_campaign_status(
    campaign_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle campaign status between ACTIVE and PAUSED on Meta and in our DB."""
    new_status = body.get("status", "").upper()
    if new_status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(status_code=400, detail="Status deve ser ACTIVE ou PAUSED")

    # Find campaign + verify tenant ownership
    result = await db.execute(
        select(Campaign, MetaAccount)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(
            Campaign.id == campaign_id,
            MetaAccount.tenant_id == current_user.tenant_id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    campaign, account = row
    client = MetaAdsClient(account.access_token, account.ad_account_id)
    try:
        await client.update_campaign_status(campaign.meta_campaign_id, new_status)
        campaign.status = new_status
        await db.flush()
        logger.info("campaign.status_updated", campaign_id=campaign_id, status=new_status)
        return {"ok": True, "status": new_status}
    except MetaAPIError as exc:
        raise HTTPException(status_code=400, detail=translate_meta_error(str(exc)))
    finally:
        await client.close()


@router.get("/{campaign_id}/detail")
async def get_campaign_detail(
    campaign_id: str,
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna detalhes de uma campanha: info, timeline diária, adsets, ads e ações."""
    since = datetime.utcnow() - timedelta(days=days)

    # Campaign + ownership check
    result = await db.execute(
        select(Campaign, MetaAccount)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(Campaign.id == campaign_id, MetaAccount.tenant_id == current_user.tenant_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    campaign, account = row

    # Daily timeline
    timeline_q = await db.execute(
        select(
            func.date_trunc("day", AdMetric.date).label("day"),
            func.sum(AdMetric.spend).label("spend"),
            func.sum(AdMetric.conversions).label("conversions"),
            func.sum(AdMetric.impressions).label("impressions"),
            func.sum(AdMetric.clicks).label("clicks"),
            func.avg(AdMetric.roas).label("roas"),
        )
        .join(Ad, AdMetric.ad_id == Ad.id)
        .join(AdSet, Ad.adset_id == AdSet.id)
        .where(AdSet.campaign_id == campaign_id, AdMetric.date >= since)
        .group_by(func.date_trunc("day", AdMetric.date))
        .order_by(func.date_trunc("day", AdMetric.date))
    )
    timeline = [
        {
            "day": r.day.date().isoformat(),
            "spend": round(float(r.spend or 0), 2),
            "conversions": int(r.conversions or 0),
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "roas": round(float(r.roas or 0), 2),
        }
        for r in timeline_q.all()
    ]

    # AdSets with aggregated metrics
    adsets_q = await db.execute(
        select(
            AdSet.id,
            AdSet.name,
            AdSet.status,
            AdSet.daily_budget,
            func.sum(AdMetric.spend).label("spend"),
            func.sum(AdMetric.conversions).label("conversions"),
            func.sum(AdMetric.impressions).label("impressions"),
            func.sum(AdMetric.clicks).label("clicks"),
            func.avg(AdMetric.roas).label("roas"),
            func.avg(AdMetric.cpa).label("cpa"),
            func.avg(AdMetric.ctr).label("ctr"),
            func.avg(AdMetric.frequency).label("frequency"),
        )
        .join(Ad, Ad.adset_id == AdSet.id)
        .join(AdMetric, and_(AdMetric.ad_id == Ad.id, AdMetric.date >= since))
        .where(AdSet.campaign_id == campaign_id)
        .group_by(AdSet.id, AdSet.name, AdSet.status, AdSet.daily_budget)
        .order_by(func.sum(AdMetric.spend).desc())
    )
    adsets = [
        {
            "id": str(r.id),
            "name": r.name,
            "status": r.status,
            "daily_budget": r.daily_budget,
            "spend": round(float(r.spend or 0), 2),
            "conversions": int(r.conversions or 0),
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "roas": round(float(r.roas or 0), 2),
            "cpa": round(float(r.cpa or 0), 2),
            "ctr": round(float(r.ctr or 0), 2),
            "frequency": round(float(r.frequency or 0), 2),
        }
        for r in adsets_q.all()
    ]

    # Recent agent actions for this campaign
    actions_q = await db.execute(
        select(AgentAction)
        .where(
            AgentAction.tenant_id == current_user.tenant_id,
            AgentAction.entity_id == campaign_id,
        )
        .order_by(AgentAction.created_at.desc())
        .limit(20)
    )
    actions = [
        {
            "id": str(a.id),
            "action_type": a.action_type,
            "status": a.status,
            "payload": a.payload,
            "created_at": a.created_at.isoformat(),
            "executed_at": a.executed_at.isoformat() if a.executed_at else None,
            "error": a.error,
        }
        for a in actions_q.scalars().all()
    ]

    # Totals for the period
    total_spend = sum(d["spend"] for d in timeline)
    total_conversions = sum(d["conversions"] for d in timeline)

    return {
        "id": campaign_id,
        "meta_campaign_id": campaign.meta_campaign_id,
        "name": campaign.name,
        "status": campaign.status,
        "objective": campaign.objective,
        "daily_budget": campaign.daily_budget,
        "account_name": account.name,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "period_days": days,
        "total_spend": round(total_spend, 2),
        "total_conversions": total_conversions,
        "timeline": timeline,
        "adsets": adsets,
        "actions": actions,
    }


class DuplicateRequest(BaseModel):
    new_name: str

    @field_validator("new_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome é obrigatório")
        return v


@router.post("/{campaign_id}/duplicate")
async def duplicate_campaign_endpoint(
    campaign_id: str,
    body: DuplicateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Duplica uma campanha no Meta (deep copy: inclui adsets e ads).
    A cópia é criada PAUSED com o novo nome informado.
    """
    result = await db.execute(
        select(Campaign, MetaAccount)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(Campaign.id == campaign_id, MetaAccount.tenant_id == current_user.tenant_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    campaign, account = row
    client = MetaAdsClient(account.access_token, account.ad_account_id)

    try:
        # 1. Duplica no Meta
        copy_result = await client.duplicate_campaign(campaign.meta_campaign_id)
        new_meta_id = copy_result.get("copied_campaign_id")
        if not new_meta_id:
            raise HTTPException(status_code=400, detail="Meta não retornou ID da campanha copiada")

        # 2. Renomeia para o nome escolhido
        await client.rename_campaign(new_meta_id, body.new_name)

        logger.info("campaign.duplicated",
                    original_id=campaign_id, new_meta_id=new_meta_id, new_name=body.new_name)

        # 3. Sincroniza nova campanha no banco via Scanner
        try:
            from app.agents.scanner.service import ScannerService
            scanner = ScannerService(db)
            await scanner.run(str(current_user.tenant_id))
            await db.commit()
        except Exception as scan_exc:
            logger.warning("campaign.duplicate_scanner_failed", error=str(scan_exc))

        return {
            "ok": True,
            "new_meta_campaign_id": new_meta_id,
            "new_name": body.new_name,
            "message": f"Campanha '{body.new_name}' criada com sucesso e pausada.",
        }

    except MetaAPIError as exc:
        raise HTTPException(status_code=400, detail=translate_meta_error(str(exc)))
    finally:
        await client.close()


class BudgetUpdateRequest(BaseModel):
    daily_budget_brl: float

    @field_validator("daily_budget_brl")
    @classmethod
    def budget_minimum(cls, v: float) -> float:
        if v < 6:
            raise ValueError("Orçamento mínimo é R$ 6,00 por dia")
        return v


@router.put("/{campaign_id}/budget")
async def update_campaign_budget(
    campaign_id: str,
    body: BudgetUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza o orçamento diário de uma campanha no Meta e no banco local."""
    result = await db.execute(
        select(Campaign, MetaAccount)
        .join(MetaAccount, Campaign.meta_account_id == MetaAccount.id)
        .where(Campaign.id == campaign_id, MetaAccount.tenant_id == current_user.tenant_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    campaign, account = row
    client = MetaAdsClient(account.access_token, account.ad_account_id)
    daily_budget_cents = int(body.daily_budget_brl * 100)

    try:
        await client.update_campaign_budget(campaign.meta_campaign_id, daily_budget_cents)
        campaign.daily_budget = body.daily_budget_brl
        await db.flush()
        logger.info("campaign.budget_updated", campaign_id=campaign_id, budget=body.daily_budget_brl)
        return {"ok": True, "daily_budget": body.daily_budget_brl}
    except MetaAPIError as exc:
        raise HTTPException(status_code=400, detail=translate_meta_error(str(exc)))
    finally:
        await client.close()


@router.get("/objectives")
async def list_objectives(_: User = Depends(get_current_user)):
    """Return available objectives with wizard labels."""
    return [{"key": k, **v} for k, v in OBJECTIVE_LABELS.items()]


@router.get("/pages")
async def list_pages(
    account_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return Facebook Pages accessible for this ad account's token."""
    _, client = await _get_account_client(account_id, str(current_user.tenant_id), db)
    try:
        pages = await client.get_pages()
        return pages
    except MetaAPIError as exc:
        raise HTTPException(status_code=400, detail=translate_meta_error(str(exc)))
    finally:
        await client.close()


@router.post("/upload-image")
async def upload_image(
    account_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image to Meta Ads image library. Returns image_hash for use in campaign creation."""
    if file.content_type not in ("image/jpeg", "image/jpg", "image/png"):
        raise HTTPException(status_code=400, detail="Use apenas imagens JPG ou PNG")

    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagem muito grande. Máximo 30 MB")

    _, client = await _get_account_client(account_id, str(current_user.tenant_id), db)
    try:
        result = await client.upload_image(content, file.filename or "image.jpg")
        if not result.get("hash"):
            raise HTTPException(status_code=400, detail="Falha ao fazer upload da imagem no Meta")
        return {"image_hash": result["hash"], "image_url": result.get("url")}
    except MetaAPIError as exc:
        raise HTTPException(status_code=400, detail=translate_meta_error(str(exc)))
    finally:
        await client.close()


@router.post("/create", response_model=CreateCampaignResult)
async def create_campaign(
    body: CampaignCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a campaign (+ adset + optional ad) on Meta Ads.
    Everything is created PAUSED — the user activates manually.
    If any step fails after a prior step succeeded, we delete what was created (rollback).
    """
    _, client = await _get_account_client(body.account_id, str(current_user.tenant_id), db)

    meta_objective = OBJECTIVE_MAP[body.objective]
    optimization_goal = OPTIMIZATION_MAP[meta_objective]
    billing_event = BILLING_MAP[meta_objective]
    daily_budget_cents = int(body.daily_budget_brl * 100)

    # Build targeting
    gender_map = {"men": 1, "women": 2}
    genders = [gender_map[g] for g in body.genders if g in gender_map] or [1, 2]
    targeting = {
        "geo_locations": {"countries": body.countries},
        "age_min": body.age_min,
        "age_max": body.age_max,
        "genders": genders,
    }

    meta_campaign_id: Optional[str] = None
    meta_adset_id: Optional[str] = None
    meta_creative_id: Optional[str] = None
    meta_ad_id: Optional[str] = None

    try:
        # Step 1 — Campaign
        meta_campaign_id = await client.create_campaign(
            name=body.campaign_name,
            objective=meta_objective,
            daily_budget_cents=daily_budget_cents,
        )
        logger.info("campaign.created", campaign_id=meta_campaign_id)

        # Step 2 — AdSet
        adset_name = f"{body.campaign_name} — Público Principal"
        meta_adset_id = await client.create_adset(
            campaign_id=meta_campaign_id,
            name=adset_name,
            daily_budget_cents=daily_budget_cents,
            optimization_goal=optimization_goal,
            billing_event=billing_event,
            targeting=targeting,
        )
        logger.info("adset.created", adset_id=meta_adset_id)

        # Step 3 — Ad Creative + Ad (only if full ad data provided)
        has_ad_data = all([body.page_id, body.headline, body.body, body.link_url, body.image_hash])
        if has_ad_data:
            cta_type = CTA_MAP.get(body.cta_label or "Saiba mais", "LEARN_MORE")
            meta_creative_id = await client.create_image_creative(
                page_id=body.page_id,
                image_hash=body.image_hash,
                headline=body.headline,
                body=body.body,
                link=body.link_url,
                cta_type=cta_type,
            )
            logger.info("creative.created", creative_id=meta_creative_id)

            meta_ad_id = await client.create_ad(
                adset_id=meta_adset_id,
                name=body.campaign_name,
                creative_id=meta_creative_id,
            )
            logger.info("ad.created", ad_id=meta_ad_id)

        # Trigger scanner to sync new entities into DB
        try:
            from app.agents.scanner.service import ScannerService
            scanner = ScannerService(db)
            await scanner.run(str(current_user.tenant_id))
            await db.commit()
        except Exception as scan_exc:
            logger.warning("campaign.create_scanner_failed", error=str(scan_exc))

        message = "Campanha criada com sucesso e pausada. Ative quando quiser começar a veicular."
        if not has_ad_data:
            message = "Campanha e conjunto de anúncios criados. Adicione um anúncio para começar a veicular."

        return CreateCampaignResult(
            meta_campaign_id=meta_campaign_id,
            meta_adset_id=meta_adset_id,
            meta_ad_id=meta_ad_id,
            message=message,
        )

    except MetaAPIError as exc:
        # Rollback: delete what was created (best-effort)
        logger.error("campaign.create_failed", error=str(exc))
        if meta_adset_id:
            await client.delete_object(meta_adset_id)
        if meta_campaign_id:
            await client.delete_object(meta_campaign_id)
        raise HTTPException(status_code=400, detail=translate_meta_error(str(exc)))

    except HTTPException:
        raise

    except Exception as exc:
        logger.error("campaign.create_unexpected", error=str(exc))
        if meta_adset_id:
            await client.delete_object(meta_adset_id)
        if meta_campaign_id:
            await client.delete_object(meta_campaign_id)
        raise HTTPException(status_code=500, detail="Erro inesperado ao criar campanha. Tente novamente.")

    finally:
        await client.close()
