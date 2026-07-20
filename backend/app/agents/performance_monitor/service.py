"""
Performance Monitor — análise contínua 24h das campanhas Blaze.
Roda a cada 6 horas. Mensagens detalhadas por marca com métricas completas.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentBase
from app.core.logging import logger

from app.core.config import settings

BLAZE_ACCOUNT_ID = "1191928981271362"
META_BASE = "https://graph.facebook.com/v21.0"

# Agrupa conjuntos por marca
BRAND_MAP = {
    "Circo do tiru": "Circo do Tiru",
    "MMABET":        "MMABET",
    "Mmabet":        "MMABET",
    "Donald Bet":    "Donald Bet",
    "Lance da sorte":"Lance da Sorte",
    "Bet Esporte":   "Bet Esporte",
    "Zona de Jogo":  "Zona de Jogo",
    "Aposta Online": "Aposta Online",
    "7k Bet":        "7k Bet",
    "Vera Bet":      "Vera Bet",
    "blaze":         "Blaze",
}

# Objetivo por conjunto (purchase ou signup)
OBJECTIVES = {
    "Circo do tiru": "purchase",
    "MMABET / RT":   "purchase",
    "Mmabet UA":     "signup",
    "MMABET / UA":   "signup",
    "Donald Bet":    "signup",
    "Lance da sorte":"signup",
    "Bet Esporte":   "signup",
    "Zona de Jogo":  "purchase",
    "Aposta Online": "purchase",
    "7k Bet":        "signup",
    "Vera Bet":      "purchase",
    "blaze":         "signup",
}

BENCHMARKS = {
    "purchase": {"roas_min": 3.0, "roas_critical": 2.0, "cpa_max": 4.50, "freq_max": 3.5},
    "signup":   {"cpl_max": 2.50, "cpl_critical": 3.50, "freq_max": 4.0},
}


def _brand(name: str) -> str:
    for key, brand in BRAND_MAP.items():
        if key.lower() in name.lower():
            return brand
    return "Outros"


def _objective(name: str) -> str:
    for key, obj in OBJECTIVES.items():
        if key.lower() in name.lower():
            return obj
    return "purchase"


def _status_icon(severity: str) -> str:
    return {"ok": "✅", "warning": "⚠️", "critical": "🔴", "opportunity": "🚀"}.get(severity, "•")


class PerformanceMonitor(AgentBase):
    name = "performance_monitor"

    def __init__(self, session: AsyncSession):
        super().__init__(session, "")
        self.session = session
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def run(self, tenant_id: str) -> dict:
        self._tenant_id = tenant_id
        logger.info("performance_monitor.start", tenant_id=tenant_id)

        token = await self._get_blaze_token()
        if not token:
            return {"status": "skipped", "reason": "token não encontrado"}

        metrics = await self._fetch_metrics(token)
        if not metrics:
            return {"status": "skipped", "reason": "sem dados"}

        brands = self._group_by_brand(metrics)
        analysis = self._analyze(brands)

        # Carrega métricas da verificação anterior para mostrar deltas
        self._prev_metrics = self._load_prev_brand_metrics(tenant_id)

        message = self._build_message(brands, analysis)

        # Salva métricas atuais para próxima comparação
        self._save_brand_metrics(brands, tenant_id)
        await self._send_telegram(message)
        await self._save_to_brain(analysis, message, tenant_id, brands)

        # Publica na Knowledge Base para Analyst/Doctor/Decision lerem
        await self._publish_to_kb(brands, analysis, tenant_id)

        # Alerta proativo imediato se crítico
        if analysis["critical"]:
            await self._send_critical_alert(analysis, tenant_id)

        logger.info("performance_monitor.done",
                    brands=len(brands),
                    alerts=len(analysis["alerts"]),
                    critical=analysis["critical"])

        total_spend_7d = round(sum(b["last7d"]["spend"] for b in brands.values()), 2)

        return {
            "status": "ok",
            "brands": len(brands),
            "alerts": len(analysis["alerts"]),
            "opportunities": len(analysis["opportunities"]),
            "critical": analysis["critical"],
            "report": message,
            "alerts_data": analysis["alerts"],
            "opportunities_data": analysis["opportunities"],
            "total_spend_7d": total_spend_7d,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def _publish_to_kb(self, brands: dict, analysis: dict, tenant_id: str) -> None:
        """Publica estado das campanhas na Knowledge Base para os outros agentes."""
        try:
            brand_summary = []
            for b in brands.values():
                p7 = b["last7d"]
                brand_summary.append({
                    "brand": b["name"],
                    "spend_7d": p7["spend"],
                    "roas": p7["roas"],
                    "cpl": p7["cpl"],
                    "purchases": p7["purchases"],
                    "signups": p7["signups"],
                })

            severity = "critical" if analysis["critical"] else (
                "high" if any(a["severity"] == "warning" for a in analysis["alerts"]) else "low"
            )

            await self.publish_knowledge(
                topic="monitor_report",
                entry_type="raw_data",
                content={
                    "brands": brand_summary,
                    "alerts": analysis["alerts"],
                    "opportunities": analysis["opportunities"],
                    "critical": analysis["critical"],
                    "generated_at": datetime.utcnow().isoformat(),
                },
                summary=(
                    f"Monitor Blaze: {len(brands)} marcas analisadas. "
                    f"{len(analysis['alerts'])} alertas, {len(analysis['opportunities'])} oportunidades. "
                    f"{'CRÍTICO' if analysis['critical'] else 'Dentro do esperado'}."
                ),
                confidence=1.0,
                ttl_hours=7,
            )
        except Exception as e:
            logger.warning("performance_monitor.kb_publish_failed", error=str(e))

    async def _send_critical_alert(self, analysis: dict, tenant_id: str) -> None:
        """Envia alerta imediato no Telegram quando há situação crítica."""
        from sqlalchemy import text
        try:
            result = await self.session.execute(
                text("SELECT telegram_chat_id FROM tenants WHERE id = :tid LIMIT 1"),
                {"tid": tenant_id},
            )
            row = result.fetchone()
            chat_id = row[0] if row else None
            if not chat_id:
                return

            tg_token = settings.TELEGRAM_BOT_TOKEN
            if not tg_token:
                return

            critical_msgs = [
                f"🔴 {a['brand']}: {a['msg']}"
                for a in analysis["alerts"] if a["severity"] == "critical"
            ]
            text_msg = (
                "🚨 *ALERTA CRÍTICO — D10 Meta AI*\n\n"
                + "\n".join(critical_msgs)
                + "\n\n⚡ Acesse o app para tomar uma ação agora."
            )

            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    data={"chat_id": chat_id, "text": text_msg, "parse_mode": "Markdown"},
                )
            logger.info("performance_monitor.critical_alert_sent")
        except Exception as e:
            logger.warning("performance_monitor.critical_alert_failed", error=str(e))

    async def _get_blaze_token(self) -> str | None:
        from sqlalchemy import text
        result = await self.session.execute(
            text("SELECT access_token FROM meta_accounts WHERE name = 'Blaze' AND is_active = true LIMIT 1")
        )
        row = result.fetchone()
        return row[0] if row else None

    async def _fetch_metrics(self, token: str) -> list[dict]:
        """Busca métricas para 3 períodos em paralelo: hoje, ontem e 7 dias."""
        filters = '[{"field":"adset.effective_status","operator":"IN","value":["ACTIVE"]}]'
        ins_fields = "spend,actions,action_values,impressions,reach,frequency,ctr,cpm"

        fields = (
            f"name,status,bid_amount,"
            f"today:insights.date_preset(today){{{ins_fields}}},"
            f"yesterday:insights.date_preset(yesterday){{{ins_fields}}},"
            f"last7d:insights.date_preset(last_7d){{{ins_fields}}}"
        )

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{META_BASE}/act_{BLAZE_ACCOUNT_ID}/adsets",
                params={"fields": fields, "limit": 100, "access_token": token, "filtering": filters},
            )
            data = resp.json()

        def _parse(ins_data: list) -> dict:
            ins = ins_data[0] if ins_data else {}
            actions = {a["action_type"]: float(a["value"]) for a in ins.get("actions", [])}
            av = {a["action_type"]: float(a["value"]) for a in ins.get("action_values", [])}
            purchases = int(actions.get("offsite_conversion.fb_pixel_purchase", 0))
            signups   = int(actions.get("offsite_conversion.fb_pixel_complete_registration", 0))
            revenue   = av.get("offsite_conversion.fb_pixel_purchase", 0.0)
            spend     = float(ins.get("spend", 0))
            return {
                "spend": spend,
                "purchases": purchases,
                "signups": signups,
                "revenue": revenue,
                "impressions": int(ins.get("impressions", 0)),
                "frequency": round(float(ins.get("frequency", 0)), 2),
                "ctr": round(float(ins.get("ctr", 0)), 2),
                "roas": round(revenue / spend, 2) if spend > 0 and revenue > 0 else None,
                "cpa":  round(spend / purchases, 2) if purchases > 0 else None,
                "cpl":  round(spend / signups, 2)   if signups > 0 else None,
            }

        results = []
        for adset in data.get("data", []):
            today     = _parse(adset.get("today", {}).get("data", []))
            yesterday = _parse(adset.get("yesterday", {}).get("data", []))
            last7d    = _parse(adset.get("last7d", {}).get("data", []))

            if last7d["spend"] < 5:
                continue

            results.append({
                "id":        adset["id"],
                "name":      adset["name"],
                "brand":     _brand(adset["name"]),
                "objective": _objective(adset["name"]),
                "today":     today,
                "yesterday": yesterday,
                "last7d":    last7d,
                # atalhos para análise (usa 7d)
                "spend":     last7d["spend"],
                "purchases": last7d["purchases"],
                "signups":   last7d["signups"],
                "roas":      last7d["roas"],
                "cpa":       last7d["cpa"],
                "cpl":       last7d["cpl"],
            })

        return results

    def _group_by_brand(self, metrics: list[dict]) -> dict:
        brands: dict[str, dict] = {}
        for m in metrics:
            b = m["brand"]
            if b not in brands:
                brands[b] = {
                    "name": b, "adsets": [],
                    "today":     {"spend": 0.0, "purchases": 0, "signups": 0, "revenue": 0.0},
                    "yesterday": {"spend": 0.0, "purchases": 0, "signups": 0, "revenue": 0.0},
                    "last7d":    {"spend": 0.0, "purchases": 0, "signups": 0, "revenue": 0.0},
                }
            brands[b]["adsets"].append(m)
            for period in ("today", "yesterday", "last7d"):
                for k in ("spend", "purchases", "signups", "revenue"):
                    brands[b][period][k] += m[period].get(k, 0)

        # Calcula ROAS/CPA/CPL por período
        for b in brands.values():
            for period in ("today", "yesterday", "last7d"):
                p = b[period]
                p["roas"] = round(p["revenue"] / p["spend"], 2) if p["spend"] > 0 and p["revenue"] > 0 else None
                p["cpa"]  = round(p["spend"] / p["purchases"], 2) if p["purchases"] > 0 else None
                p["cpl"]  = round(p["spend"] / p["signups"], 2) if p["signups"] > 0 else None

        return brands

    def _analyze(self, brands: dict) -> dict:
        alerts = []
        opportunities = []
        critical = False

        for b in brands.values():
            # Determina objetivo predominante
            purchase_sets = sum(1 for a in b["adsets"] if a["objective"] == "purchase")
            obj = "purchase" if purchase_sets > len(b["adsets"]) / 2 else "signup"
            bench = BENCHMARKS[obj]

            if obj == "purchase" and b["roas"] is not None:
                if b["roas"] < bench["roas_critical"]:
                    alerts.append({"severity": "critical", "brand": b["name"],
                                   "msg": f"ROAS {b['roas']:.2f}x — PAUSAR urgente"})
                    critical = True
                elif b["roas"] < bench["roas_min"]:
                    alerts.append({"severity": "warning", "brand": b["name"],
                                   "msg": f"ROAS {b['roas']:.2f}x abaixo do mínimo ({bench['roas_min']}x)"})
                elif b["roas"] >= 5.0:
                    opportunities.append({"brand": b["name"],
                                          "msg": f"ROAS {b['roas']:.2f}x — escalar orçamento +20%"})

            if obj == "signup" and b["cpl"] is not None:
                if b["cpl"] > bench["cpl_critical"]:
                    alerts.append({"severity": "critical", "brand": b["name"],
                                   "msg": f"CPL R${b['cpl']:.2f} — revisar público urgente"})
                    critical = True
                elif b["cpl"] > bench["cpl_max"]:
                    alerts.append({"severity": "warning", "brand": b["name"],
                                   "msg": f"CPL R${b['cpl']:.2f} acima do máximo (R${bench['cpl_max']:.2f})"})
                elif b["cpl"] and b["cpl"] <= 1.20:
                    opportunities.append({"brand": b["name"],
                                          "msg": f"CPL R${b['cpl']:.2f} — escalar orçamento +30%"})

        return {"alerts": alerts, "opportunities": opportunities, "critical": critical}

    def _load_prev_brand_metrics(self, tenant_id: str) -> dict:
        """Carrega métricas da verificação anterior para calcular deltas."""
        try:
            from app.core import brain
            return brain.read("monitor/prev_brand_metrics", tenant_id=tenant_id, default={})
        except Exception:
            return {}

    def _save_brand_metrics(self, brands: dict, tenant_id: str) -> None:
        """Salva métricas atuais para comparação na próxima verificação."""
        try:
            from app.core import brain
            snapshot = {}
            for name, b in brands.items():
                p7 = b["last7d"]
                adsets = b["adsets"]
                total_clicks = sum(a["last7d"].get("impressions", 0) * a["last7d"].get("ctr", 0) / 100
                                   for a in adsets if a["last7d"].get("ctr"))
                total_imp = sum(a["last7d"].get("impressions", 0) for a in adsets)
                cpc = round(p7["spend"] / total_clicks, 2) if total_clicks > 0 else None
                conv_total = p7["purchases"] + p7["signups"]
                conv_rate = round(conv_total / total_clicks * 100, 2) if total_clicks > 0 else None
                snapshot[name] = {
                    "spend": p7["spend"],
                    "purchases": p7["purchases"],
                    "signups": p7["signups"],
                    "roas": p7["roas"],
                    "cpa": p7["cpa"],
                    "cpl": p7["cpl"],
                    "cpc": cpc,
                    "conv_rate": conv_rate,
                    "impressions": total_imp,
                }
            brain.write("monitor/prev_brand_metrics", snapshot, tenant_id=tenant_id)
        except Exception:
            pass

    def _build_message(self, brands: dict, analysis: dict) -> str:
        now = datetime.now()
        today_str = now.strftime("%d/%m/%Y")
        time_str  = now.strftime("%H:%M")

        def _delta(curr, prev, invert=False):
            """Retorna string de variação com seta e %. invert=True = queda é bom."""
            if curr is None or prev is None or prev == 0:
                return ""
            pct = (curr - prev) / abs(prev) * 100
            if abs(pct) < 2:
                return " (estavel)"
            arrow = "↑" if pct > 0 else "↓"
            good = (pct < 0) if invert else (pct > 0)
            sign = "+" if pct > 0 else ""
            tag = "BOM" if good else "ATENCAO"
            return f" {arrow}{sign}{pct:.1f}% [{tag}]"

        def _totals(period: str):
            spend = sum(b[period]["spend"] for b in brands.values())
            purchases = sum(b[period]["purchases"] for b in brands.values())
            signups = sum(b[period]["signups"] for b in brands.values())
            revenue = sum(b[period]["revenue"] for b in brands.values())
            roas = round(revenue / spend, 2) if spend > 0 and revenue > 0 else None
            return spend, purchases, signups, roas

        t_spend, t_purch, t_sign, t_roas = _totals("today")
        y_spend, y_purch, y_sign, y_roas = _totals("yesterday")
        w_spend, w_purch, w_sign, w_roas = _totals("last7d")

        lines = [
            "═══════════════════════════════",
            "   D10 META AI — RELATORIO",
            f"   {today_str}  {time_str} (Brasilia)",
            "═══════════════════════════════",
            "",
            "RESUMO GERAL (7 dias / hoje)",
            f"Gasto:    R${w_spend:,.2f}  /  R${t_spend:,.2f} hoje",
            f"Vendas:   {w_purch} total  /  {t_purch} hoje",
            f"Cadastros:{w_sign} total  /  {t_sign} hoje",
            f"ROAS:     {(str(w_roas)+'x') if w_roas else '-'}  /  {(str(t_roas)+'x') if t_roas else '-'} hoje",
            "",
        ]

        sorted_brands = sorted(brands.values(), key=lambda b: -b["last7d"]["spend"])

        for b in sorted_brands:
            p7  = b["last7d"]
            pt  = b["today"]
            py  = b["yesterday"]
            prev = self._prev_metrics.get(b["name"], {})

            obj_sets = [a for a in b["adsets"] if a["objective"] == "purchase"]
            is_purchase = len(obj_sets) > len(b["adsets"]) / 2

            # Calcula CPC e taxa de conversão agregados dos adsets
            total_clicks = 0
            total_imp = 0
            for a in b["adsets"]:
                imp = a["last7d"].get("impressions", 0)
                ctr_val = a["last7d"].get("ctr", 0)
                total_imp += imp
                total_clicks += round(imp * ctr_val / 100) if imp and ctr_val else 0

            cpc = round(p7["spend"] / total_clicks, 2) if total_clicks > 0 else None
            conv_total = p7["purchases"] + p7["signups"]
            conv_rate  = round(conv_total / total_clicks * 100, 2) if total_clicks > 0 else None

            # Status
            if is_purchase and p7["roas"]:
                if p7["roas"] >= 4.0:   status_icon = "✅"
                elif p7["roas"] >= 2.5: status_icon = "⚠️"
                else:                   status_icon = "🔴"
            elif not is_purchase and p7["cpl"]:
                if p7["cpl"] <= 1.50:   status_icon = "✅"
                elif p7["cpl"] <= 2.50: status_icon = "⚠️"
                else:                   status_icon = "🔴"
            else:
                status_icon = "⚪"

            lines.append(f"───────────────────────────────")
            lines.append(f"{status_icon} {b['name'].upper()}")
            lines.append("")

            # Gasto
            d_spend = _delta(p7["spend"], prev.get("spend"), invert=False)
            lines.append(f"  Gasto 7d:    R${p7['spend']:,.2f}{d_spend}")
            lines.append(f"  Gasto hoje:  R${pt['spend']:,.2f}  |  Ontem: R${py['spend']:,.2f}")
            lines.append("")

            # Vendas / Registros
            d_purch = _delta(p7["purchases"], prev.get("purchases"))
            d_sign  = _delta(p7["signups"],   prev.get("signups"))
            lines.append(f"  Vendas 7d:   {p7['purchases']}{d_purch}")
            lines.append(f"  Registros 7d:{p7['signups']}{d_sign}")
            lines.append(f"  Hoje:        {pt['purchases']} vendas / {pt['signups']} cadastros")
            lines.append("")

            # ROAS / CPA / CPL
            if is_purchase and p7["roas"]:
                d_roas = _delta(p7["roas"], prev.get("roas"))
                lines.append(f"  ROAS 7d:     {p7['roas']:.2f}x{d_roas}")
            if p7["cpa"]:
                d_cpa = _delta(p7["cpa"], prev.get("cpa"), invert=True)
                lines.append(f"  CPA (compra):R${p7['cpa']:.2f}{d_cpa}")
            if p7["cpl"]:
                d_cpl = _delta(p7["cpl"], prev.get("cpl"), invert=True)
                lines.append(f"  CPL (cad):   R${p7['cpl']:.2f}{d_cpl}")
            lines.append("")

            # CPC e Taxa de Conversão
            if cpc:
                d_cpc = _delta(cpc, prev.get("cpc"), invert=True)
                lines.append(f"  CPC 7d:      R${cpc:.2f}{d_cpc}")
            if conv_rate is not None:
                d_cr = _delta(conv_rate, prev.get("conv_rate"))
                lines.append(f"  Taxa Conv.:  {conv_rate:.2f}%{d_cr}")
            if total_imp:
                lines.append(f"  Impressoes:  {total_imp:,}")
            lines.append("")

        lines.append("═══════════════════════════════")
        # Alertas e oportunidades
        if analysis["alerts"]:
            lines.append("ALERTAS:")
            for al in analysis["alerts"]:
                tag = "CRITICO" if al["severity"] == "critical" else "ATENCAO"
                lines.append(f"  [{tag}] {al['brand']}: {al['msg']}")
        if analysis["opportunities"]:
            lines.append("OPORTUNIDADES:")
            for op in analysis["opportunities"]:
                lines.append(f"  [ESCALAR] {op['brand']}: {op['msg']}")
        if not analysis["alerts"] and not analysis["opportunities"]:
            lines.append("STATUS: Todas campanhas dentro do esperado.")
        lines.append("═══════════════════════════════")

        return "\n".join(lines)

    async def _send_telegram(self, message: str) -> None:
        """Envia mensagem no Telegram."""
        from sqlalchemy import text
        result = await self.session.execute(
            text("SELECT telegram_chat_id FROM tenants LIMIT 1")
        )
        row = result.fetchone()
        chat_id = row[0] if row else None
        if not chat_id:
            logger.warning("performance_monitor.no_chat_id")
            return

        tg_token = settings.TELEGRAM_BOT_TOKEN
        if not tg_token:
            logger.warning("performance_monitor.no_telegram_token")
            return

        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                await client.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    data={"chat_id": chat_id, "text": chunk},
                )
        logger.info("performance_monitor.telegram_sent", chat_id=chat_id)

    async def _save_to_brain(self, analysis: dict, report: str, tenant_id: str, brands: dict | None = None) -> None:
        try:
            from app.core import brain
            spend_7d = sum(b["last7d"]["spend"] for b in brands.values()) if brands else 0
            brain.append(
                "monitor/history",
                {
                    "generated_at": datetime.utcnow().isoformat(),
                    "alerts": len(analysis["alerts"]),
                    "opportunities": len(analysis["opportunities"]),
                    "critical": analysis["critical"],
                    "spend_7d": round(spend_7d, 2),
                    "report_snippet": report[:300],
                },
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning("performance_monitor.brain_save_failed", error=str(e))
