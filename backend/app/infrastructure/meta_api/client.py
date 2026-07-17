"""Meta Ads API client with retry logic."""
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import MetaAPIError
from app.core.logging import logger

BASE_URL = f"https://graph.facebook.com/{settings.META_API_VERSION}"

INSIGHT_FIELDS = (
    "impressions,clicks,spend,actions,action_values,"
    "reach,frequency,ctr,cpc,cpm,cost_per_action_type"
)


class MetaAdsClient:
    def __init__(self, access_token: str, ad_account_id: str = ""):
        self.access_token = access_token
        self.ad_account_id = ad_account_id
        self._http = httpx.AsyncClient(timeout=30)

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        params["access_token"] = self.access_token
        resp = await self._http.get(f"{BASE_URL}{path}", params=params)
        data = resp.json()
        if "error" in data:
            raise MetaAPIError(data["error"].get("message", "Unknown error"))
        return data

    async def _post(self, path: str, params: Optional[Dict] = None, json: Optional[Dict] = None) -> Dict:
        params = params or {}
        params["access_token"] = self.access_token
        resp = await self._http.post(f"{BASE_URL}{path}", params=params, json=json or {})
        data = resp.json()
        if "error" in data:
            raise MetaAPIError(data["error"].get("message", "Unknown error"))
        return data

    # ── OAuth helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def get_oauth_url(redirect_uri: str, state: str = "") -> str:
        """Retorna a URL de autorização do Facebook OAuth."""
        import urllib.parse
        params = {
            "client_id": settings.META_APP_ID,
            "redirect_uri": redirect_uri,
            "scope": "ads_read,ads_management,business_management,read_insights",
            "response_type": "code",
            "state": state,
        }
        # Usa config_id do Facebook Login for Business se disponível
        if settings.META_CONFIG_ID:
            params["config_id"] = settings.META_CONFIG_ID
        return "https://www.facebook.com/dialog/oauth?" + urllib.parse.urlencode(params)

    @staticmethod
    async def exchange_code_for_token(code: str, redirect_uri: str) -> Dict:
        """Troca o código OAuth por short-lived token."""
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"{BASE_URL}/oauth/access_token",
                params={
                    "client_id": settings.META_APP_ID,
                    "client_secret": settings.META_APP_SECRET,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            data = resp.json()
            if "error" in data:
                raise MetaAPIError(data["error"].get("message", "Token exchange failed"))
            return data  # {"access_token": ..., "token_type": "bearer"}

    @staticmethod
    async def exchange_long_lived_token(short_token: str) -> Dict:
        """Troca short-lived token por long-lived token (60 dias)."""
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"{BASE_URL}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": settings.META_APP_ID,
                    "client_secret": settings.META_APP_SECRET,
                    "fb_exchange_token": short_token,
                },
            )
            data = resp.json()
            if "error" in data:
                raise MetaAPIError(data["error"].get("message", "Long-lived token exchange failed"))
            return data  # {"access_token": ..., "token_type": "bearer", "expires_in": ...}

    async def validate_token(self) -> Dict:
        """Valida o token e retorna informações do usuário/app."""
        data = await self._get("/me", {"fields": "id,name"})
        return data  # {"id": ..., "name": ...}

    async def debug_token(self, token_to_debug: str) -> Dict:
        """Inspeciona um token via /debug_token (requer app token)."""
        app_token = f"{settings.META_APP_ID}|{settings.META_APP_SECRET}"
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"{BASE_URL}/debug_token",
                params={
                    "input_token": token_to_debug,
                    "access_token": app_token,
                },
            )
            return resp.json()

    async def get_user_ad_accounts(self) -> List[Dict]:
        """Lista todas as Ad Accounts acessíveis pelo token."""
        data = await self._get(
            "/me/adaccounts",
            {"fields": "id,name,account_id,account_status,currency,timezone_name,business"},
        )
        return data.get("data", [])

    # ── Campaigns / Adsets / Ads ───────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_campaigns(self) -> List[Dict]:
        path = f"/act_{self.ad_account_id}/campaigns"
        fields = "id,name,status,objective,daily_budget,lifetime_budget"
        data = await self._get(path, {"fields": fields, "limit": 500})
        return data.get("data", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_adsets(self, campaign_id: str) -> List[Dict]:
        path = f"/{campaign_id}/adsets"
        fields = "id,name,status,daily_budget,targeting"
        data = await self._get(path, {"fields": fields, "limit": 500})
        return data.get("data", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_ads(self, adset_id: str) -> List[Dict]:
        path = f"/{adset_id}/ads"
        fields = "id,name,status,creative{id,object_type}"
        data = await self._get(path, {"fields": fields, "limit": 500})
        return data.get("data", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_ad_insights(self, ad_id: str, date_preset: str = "last_7d") -> Dict:
        path = f"/{ad_id}/insights"
        data = await self._get(path, {"fields": INSIGHT_FIELDS, "date_preset": date_preset})
        items = data.get("data", [])
        return items[0] if items else {}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_ad_insights_daily(self, ad_id: str, days: int = 30) -> List[Dict]:
        """Retorna insights diários para os últimos N dias (um item por dia)."""
        path = f"/{ad_id}/insights"
        data = await self._get(path, {
            "fields": INSIGHT_FIELDS,
            "date_preset": f"last_{days}d",
            "time_increment": 1,
        })
        return data.get("data", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_campaign_insights(self, campaign_id: str, date_preset: str = "last_7d") -> Dict:
        path = f"/{campaign_id}/insights"
        data = await self._get(path, {"fields": INSIGHT_FIELDS, "date_preset": date_preset})
        items = data.get("data", [])
        return items[0] if items else {}

    # ── Mutation helpers ───────────────────────────────────────────────────────

    async def update_ad_status(self, ad_id: str, status: str) -> Dict:
        resp = await self._http.post(
            f"{BASE_URL}/{ad_id}",
            params={"access_token": self.access_token},
            json={"status": status},
        )
        return resp.json()

    async def update_campaign_status(self, campaign_id: str, status: str) -> Dict:
        resp = await self._http.post(
            f"{BASE_URL}/{campaign_id}",
            params={"access_token": self.access_token},
            json={"status": status},
        )
        return resp.json()

    async def update_campaign_budget(self, campaign_id: str, daily_budget: int) -> Dict:
        resp = await self._http.post(
            f"{BASE_URL}/{campaign_id}",
            params={"access_token": self.access_token},
            json={"daily_budget": daily_budget},
        )
        return resp.json()

    async def duplicate_campaign(self, campaign_id: str) -> Dict:
        resp = await self._http.post(
            f"{BASE_URL}/{campaign_id}/copies",
            params={"access_token": self.access_token},
            json={"deep_copy": True, "status_option": "PAUSED"},
        )
        data = resp.json()
        if "error" in data:
            raise MetaAPIError(data["error"].get("message", "Erro ao duplicar campanha"))
        return data

    async def rename_campaign(self, campaign_id: str, name: str) -> Dict:
        resp = await self._http.post(
            f"{BASE_URL}/{campaign_id}",
            params={"access_token": self.access_token},
            json={"name": name},
        )
        data = resp.json()
        if "error" in data:
            raise MetaAPIError(data["error"].get("message", "Erro ao renomear campanha"))
        return data

    # ── Creative Library ───────────────────────────────────────────────────────

    async def upload_image(self, content: bytes, filename: str) -> Dict:
        """Upload image bytes to Meta Ad Images. Returns {'hash': ..., 'url': ...}."""
        import base64
        b64 = base64.b64encode(content).decode()
        data = await self._post(
            f"/act_{self.ad_account_id}/adimages",
            params={"bytes": b64, "name": filename, "access_token": self.access_token},
        )
        images = data.get("images", {})
        # Response keys vary by filename; grab first result
        first = next(iter(images.values()), {}) if images else {}
        return {"hash": first.get("hash"), "url": first.get("url")}

    async def upload_video(self, content: bytes, filename: str) -> Dict:
        """Upload video bytes to Meta Ad Videos. Returns {'video_id': ...}."""
        import tempfile, os
        # Meta requires multipart form upload for videos
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[-1], delete=False) as f:
            f.write(content)
            tmp_path = f.name
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                with open(tmp_path, "rb") as fh:
                    resp = await client.post(
                        f"https://graph-video.facebook.com/{settings.META_API_VERSION}/act_{self.ad_account_id}/advideos",
                        params={"access_token": self.access_token},
                        files={"source": (filename, fh, "video/mp4")},
                        data={"title": filename},
                    )
                data = resp.json()
                if "error" in data:
                    raise MetaAPIError(data["error"].get("message", "Video upload error"))
                return {"video_id": data.get("id")}
        finally:
            os.unlink(tmp_path)

    # ── Campaign Creation ──────────────────────────────────────────────────────

    async def get_pages(self) -> List[Dict]:
        """Return Facebook Pages accessible by this token."""
        data = await self._get("/me/accounts", {"fields": "id,name"})
        return data.get("data", [])

    async def create_campaign(
        self,
        name: str,
        objective: str,
        daily_budget_cents: int,
    ) -> str:
        """Create a PAUSED campaign and return its Meta campaign ID."""
        data = await self._post(
            f"/act_{self.ad_account_id}/campaigns",
            json={
                "name": name,
                "objective": objective,
                "status": "PAUSED",
                "daily_budget": str(daily_budget_cents),
                "special_ad_categories": [],
            },
        )
        if "id" not in data:
            raise MetaAPIError(f"Campaign creation failed: {data}")
        return data["id"]

    async def create_adset(
        self,
        campaign_id: str,
        name: str,
        daily_budget_cents: int,
        optimization_goal: str,
        billing_event: str,
        targeting: Dict,
    ) -> str:
        """Create a PAUSED adset and return its Meta adset ID."""
        data = await self._post(
            f"/act_{self.ad_account_id}/adsets",
            json={
                "name": name,
                "campaign_id": campaign_id,
                "daily_budget": str(daily_budget_cents),
                "billing_event": billing_event,
                "optimization_goal": optimization_goal,
                "targeting": targeting,
                "status": "PAUSED",
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            },
        )
        if "id" not in data:
            raise MetaAPIError(f"AdSet creation failed: {data}")
        return data["id"]

    async def create_image_creative(
        self,
        page_id: str,
        image_hash: str,
        headline: str,
        body: str,
        link: str,
        cta_type: str = "LEARN_MORE",
    ) -> str:
        """Create a link-ad creative with an image and return creative ID."""
        data = await self._post(
            f"/act_{self.ad_account_id}/adcreatives",
            json={
                "name": f"Creative — {headline[:40]}",
                "object_story_spec": {
                    "page_id": page_id,
                    "link_data": {
                        "image_hash": image_hash,
                        "link": link,
                        "name": headline,
                        "message": body,
                        "call_to_action": {
                            "type": cta_type,
                            "value": {"link": link},
                        },
                    },
                },
            },
        )
        if "id" not in data:
            raise MetaAPIError(f"Creative creation failed: {data}")
        return data["id"]

    async def create_ad(self, adset_id: str, name: str, creative_id: str) -> str:
        """Create a PAUSED ad and return its Meta ad ID."""
        data = await self._post(
            f"/act_{self.ad_account_id}/ads",
            json={
                "name": name,
                "adset_id": adset_id,
                "creative": {"creative_id": creative_id},
                "status": "PAUSED",
            },
        )
        if "id" not in data:
            raise MetaAPIError(f"Ad creation failed: {data}")
        return data["id"]

    async def delete_object(self, object_id: str) -> None:
        """Delete any Meta Ads object (campaign/adset/ad) by ID — used for rollback."""
        try:
            await self._http.delete(
                f"{BASE_URL}/{object_id}",
                params={"access_token": self.access_token},
            )
        except Exception:
            pass  # best-effort rollback

    async def close(self):
        await self._http.aclose()
