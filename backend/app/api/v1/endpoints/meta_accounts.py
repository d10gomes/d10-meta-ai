from typing import List, Optional
from pydantic import BaseModel
import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.core.config import settings
from app.core.exceptions import MetaAPIError
from app.core.logging import logger
from app.db.models import User, MetaAccount, Tenant
from app.db.session import get_db
from app.infrastructure.meta_api.client import MetaAdsClient
from app.infrastructure.repositories.meta_account_repository import MetaAccountRepository

router = APIRouter()

OAUTH_REDIRECT_URI = f"{settings.NEXT_PUBLIC_API_URL}/api/v1/meta-accounts/oauth/callback"


# ── Schemas ────────────────────────────────────────────────────────────────────

class MetaAccountCreate(BaseModel):
    ad_account_id: str
    name: str
    access_token: str


class MetaAccountOut(BaseModel):
    id: str
    ad_account_id: str
    name: Optional[str]
    is_active: bool
    last_synced_at: Optional[str]

    class Config:
        from_attributes = True


class AdAccountInfo(BaseModel):
    """Ad account descoberta via Meta API (antes de salvar)."""
    account_id: str      # sem "act_"
    name: str
    status: int
    currency: str
    timezone: str
    business_name: Optional[str] = None


class ValidateTokenResponse(BaseModel):
    valid: bool
    user_name: Optional[str] = None
    user_id: Optional[str] = None
    ad_accounts: List[AdAccountInfo] = []
    error: Optional[str] = None


# ── CRUD básico ────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[MetaAccountOut])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = MetaAccountRepository(db)
    accounts = await repo.get_by_tenant(str(current_user.tenant_id))
    return [MetaAccountOut(
        id=str(a.id), ad_account_id=a.ad_account_id,
        name=a.name, is_active=a.is_active,
        last_synced_at=a.last_synced_at.isoformat() if a.last_synced_at else None,
    ) for a in accounts]


@router.post("/", status_code=201)
async def create_account(
    body: MetaAccountCreate,
    current_user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
):
    await _check_limit(db, current_user)

    account = MetaAccount(
        tenant_id=str(current_user.tenant_id),
        ad_account_id=body.ad_account_id,
        name=body.name,
        access_token=body.access_token,
    )
    db.add(account)
    await db.flush()
    logger.info("meta_account.created", account_id=str(account.id), ad_account_id=body.ad_account_id)
    return {"id": str(account.id)}


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: str,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    repo = MetaAccountRepository(db)
    account = await repo.get_by_id(account_id)
    if not account or str(account.tenant_id) != str(current_user.tenant_id):
        raise HTTPException(status_code=404, detail="Account not found")
    await repo.delete(account)


# ── Validação de token manual ──────────────────────────────────────────────────

@router.post("/validate-token", response_model=ValidateTokenResponse)
async def validate_token(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Valida um access_token manualmente informado.
    Retorna as Ad Accounts acessíveis para que o usuário escolha quais conectar.
    """
    token = body.get("access_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="access_token é obrigatório")

    client = MetaAdsClient(access_token=token)
    try:
        me = await client.validate_token()
        raw_accounts = await client.get_user_ad_accounts()
        ad_accounts = [
            AdAccountInfo(
                account_id=a.get("account_id") or a["id"].replace("act_", ""),
                name=a.get("name", ""),
                status=a.get("account_status", 1),
                currency=a.get("currency", "BRL"),
                timezone=a.get("timezone_name", ""),
                business_name=a.get("business", {}).get("name") if a.get("business") else None,
            )
            for a in raw_accounts
        ]
        return ValidateTokenResponse(
            valid=True,
            user_name=me.get("name"),
            user_id=me.get("id"),
            ad_accounts=ad_accounts,
        )
    except MetaAPIError as exc:
        return ValidateTokenResponse(valid=False, error=str(exc))
    except Exception as exc:
        logger.error("validate_token.error", error=str(exc))
        return ValidateTokenResponse(valid=False, error="Erro ao validar token")
    finally:
        await client.close()


@router.post("/connect-from-token", status_code=201)
async def connect_from_token(
    body: dict,
    current_user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
):
    """
    Salva uma ou mais Ad Accounts a partir de um access_token validado.
    Body: { access_token, accounts: [{account_id, name}] }
    """
    token = body.get("access_token", "")
    accounts_to_add: List[dict] = body.get("accounts", [])

    if not token or not accounts_to_add:
        raise HTTPException(status_code=400, detail="access_token e accounts são obrigatórios")

    # Tentar trocar por long-lived token
    try:
        lt = await MetaAdsClient.exchange_long_lived_token(token)
        long_token = lt.get("access_token", token)
        logger.info("meta_account.long_lived_token_obtained")
    except Exception:
        long_token = token  # usa o token original se não conseguir trocar
        logger.warning("meta_account.long_lived_token_failed_using_original")

    created = []
    for acc in accounts_to_add:
        await _check_limit(db, current_user)
        account = MetaAccount(
            tenant_id=str(current_user.tenant_id),
            ad_account_id=acc["account_id"],
            name=acc.get("name", acc["account_id"]),
            access_token=long_token,
        )
        db.add(account)
        await db.flush()
        created.append({"id": str(account.id), "ad_account_id": acc["account_id"]})
        logger.info("meta_account.created_via_token", ad_account_id=acc["account_id"])

    return {"created": created, "token_type": "long_lived" if long_token != token else "short_lived"}


# ── OAuth Flow (Facebook Login) ────────────────────────────────────────────────

@router.get("/oauth/url")
async def get_oauth_url(
    current_user: User = Depends(require_role("admin", "manager")),
):
    """Retorna a URL para iniciar o OAuth do Facebook."""
    if not settings.META_APP_ID or settings.META_APP_ID == "your-meta-app-id":
        raise HTTPException(
            status_code=400,
            detail="META_APP_ID não configurado no .env. Configure primeiro nas Configurações.",
        )
    state = str(current_user.tenant_id)  # usamos tenant_id como state para segurança
    url = MetaAdsClient.get_oauth_url(OAUTH_REDIRECT_URI, state=state)
    return {"oauth_url": url}


@router.get("/oauth/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """
    Callback do OAuth Facebook.
    Após autenticação, redireciona para o frontend com o token.
    """
    frontend_url = "http://localhost:3000/accounts"

    if error:
        logger.warning("oauth.callback_error", error=error, desc=error_description)
        return RedirectResponse(url=f"{frontend_url}?oauth_error={error}")

    if not code:
        return RedirectResponse(url=f"{frontend_url}?oauth_error=no_code")

    try:
        # 1. Troca código por short-lived token
        token_data = await MetaAdsClient.exchange_code_for_token(code, OAUTH_REDIRECT_URI)
        short_token = token_data["access_token"]

        # 2. Troca por long-lived token (60 dias)
        lt_data = await MetaAdsClient.exchange_long_lived_token(short_token)
        long_token = lt_data.get("access_token", short_token)

        logger.info("oauth.token_obtained", state=state)

        # 3. Redireciona para o frontend com o token para finalizar a conexão
        import urllib.parse
        return RedirectResponse(
            url=f"{frontend_url}?oauth_token={urllib.parse.quote(long_token)}&tenant_state={state}"
        )
    except Exception as exc:
        logger.error("oauth.callback_failed", error=str(exc))
        import urllib.parse
        return RedirectResponse(
            url=f"{frontend_url}?oauth_error={urllib.parse.quote(str(exc))}"
        )


# ── Helpers internos ───────────────────────────────────────────────────────────

async def _check_limit(db: AsyncSession, current_user: User):
    repo = MetaAccountRepository(db)
    count = await repo.count_by_tenant(str(current_user.tenant_id))
    result = await db.execute(
        sqlalchemy.select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    max_accounts = tenant.max_meta_accounts if tenant else 15
    if count >= max_accounts:
        raise HTTPException(status_code=429, detail=f"Limite de {max_accounts} contas Meta atingido")
