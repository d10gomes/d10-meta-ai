"""
Performance Monitor — análise contínua 24h das campanhas Blaze.
Roda a cada 6 horas. Mensagens detalhadas por marca com métricas completas.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger

BLAZE_ACCOUNT_ID = "1191928981271362"
META_BASE = "https://graph.facebook.com/v21.0"
TG_TOKEN = "8977629545:AAFY3QF9LOSdbFAI5dNhwzX8hYvaveQGYKw"

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


class PerformanceMonitor:

    def __init__(self, session: AsyncSession):
        self.session = session
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def run(self, tenant_id: str) -> dict:
        logger.info("performance_monitor.start", tenant_id=tenant_id)

        token = await self._get_blaze_token()
        if not token:
            return {"status": "skipped", "reason": "token não encontrado"}

        metrics = await self._fetch_metrics(token)
        if not metrics:
            return {"status": "skipped", "reason": "sem dados"}

        brands = self._group_by_brand(metrics)
        analysis = self._analyze(brands)

        # Sempre manda mensagem completa (não só quando crítico)
        message = self._build_message(brands, analysis)
        await self._send_telegram(message)
        await self._save_to_brain(analysis, message, tenant_id)

        logger.info("performance_monitor.done",
                    brands=len(brands),
                    alerts=len(analysis["alerts"]),
                    critical=analysis["critical"])

        return {
            "status": "ok",
            "brands": len(brands),
            "alerts": len(analysis["alerts"]),
            "opportunities": len(analysis["opportunities"]),
            "critical": analysis["critical"],
            "report": message,
        }

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

    def _build_message(self, brands: dict, analysis: dict) -> str:
        now = datetime.now()
        today_str = now.strftime("%d/%m/%Y")
        time_str  = now.strftime("%H:%M")

        # Totais globais por período
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
            "D10 META AI - Relatorio de Campanhas",
            f"Horario: {time_str} | Data: {today_str}",
            "",
            "RESUMO GERAL",
            f"{'Periodo':<12} {'Gasto':>10} {'Compras':>8} {'Cadastros':>10} {'ROAS':>6}",
            f"{'Hoje':<12} R${t_spend:>8,.2f} {t_purch:>8} {t_sign:>10} {(str(t_roas)+'x') if t_roas else '-':>6}",
            f"{'Ontem':<12} R${y_spend:>8,.2f} {y_purch:>8} {y_sign:>10} {(str(y_roas)+'x') if y_roas else '-':>6}",
            f"{'7 dias':<12} R${w_spend:>8,.2f} {w_purch:>8} {w_sign:>10} {(str(w_roas)+'x') if w_roas else '-':>6}",
            "",
            "=" * 34,
        ]

        sorted_brands = sorted(brands.values(), key=lambda b: -b["last7d"]["spend"])

        for b in sorted_brands:
            p7 = b["last7d"]
            pt = b["today"]
            py = b["yesterday"]
            obj_sets = [a for a in b["adsets"] if a["objective"] == "purchase"]
            is_purchase = len(obj_sets) > len(b["adsets"]) / 2

            # Status baseado em 7 dias
            if is_purchase and p7["roas"]:
                status = "BOM" if p7["roas"] >= 4.0 else ("MEDIO" if p7["roas"] >= 2.5 else "RUIM")
            elif not is_purchase and p7["cpl"]:
                status = "BOM" if p7["cpl"] <= 1.50 else ("MEDIO" if p7["cpl"] <= 2.50 else "RUIM")
            else:
                status = "SEM DADOS"

            icon = {"BOM": "[BOM]", "MEDIO": "[MEDIO]", "RUIM": "[RUIM]", "SEM DADOS": "[?]"}.get(status)

            lines.append(f"\n{icon} {b['name'].upper()}")

            # Tabela dos 3 períodos por marca
            lines.append(f"  {'Periodo':<10} {'Gasto':>9} {'Comp':>5} {'Cad':>5} {'ROAS/CPL':>9}")

            def _row(label: str, p: dict, is_pur: bool) -> str:
                perf = f"ROAS {p['roas']:.2f}x" if is_pur and p["roas"] else \
                       f"CPL R${p['cpl']:.2f}" if p["cpl"] else "-"
                return f"  {label:<10} R${p['spend']:>7,.2f} {p['purchases']:>5} {p['signups']:>5} {perf:>9}"

            lines.append(_row("Hoje",   pt, is_purchase))
            lines.append(_row("Ontem",  py, is_purchase))
            lines.append(_row("7 dias", p7, is_purchase))

            # Top 3 conjuntos por gasto (período de 7 dias)
            top = sorted(b["adsets"], key=lambda a: -a["last7d"]["spend"])[:3]
            lines.append(f"  Conjuntos ({len(b['adsets'])} ativos):")
            for a in top:
                short = a["name"].split("/")[-1].strip()[:24]
                p = a["last7d"]
                perf = f"ROAS {p['roas']:.2f}x" if p["roas"] else \
                       f"CPL R${p['cpl']:.2f}" if p["cpl"] else ""
                conv = f"{p['purchases']}c" if p["purchases"] else f"{p['signups']}cad" if p["signups"] else ""
                lines.append(f"  - {short}: R${p['spend']:,.0f} {perf} {conv}")

            lines.append("  " + "-" * 32)

        # Ações
        lines.append("\nACOES:")
        if analysis["alerts"] or analysis["opportunities"]:
            for al in analysis["alerts"]:
                tag = "[CRITICO]" if al["severity"] == "critical" else "[ATENCAO]"
                lines.append(f"{tag} {al['brand']}: {al['msg']}")
            for op in analysis["opportunities"]:
                lines.append(f"[ESCALAR] {op['brand']}: {op['msg']}")
        else:
            lines.append("Todas as campanhas dentro do esperado.")

        return "\n".join(lines)

    async def _send_telegram(self, message: str) -> None:
        """Envia mensagem no Telegram."""
        from sqlalchemy import text
        result = await self.session.execute(
            text("SELECT whatsapp_number FROM tenants LIMIT 1")
        )
        row = result.fetchone()
        chat_id = row[0] if row else None
        if not chat_id:
            logger.warning("performance_monitor.no_chat_id")
            return

        # Telegram limita mensagens a 4096 chars — divide se necessário
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                await client.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    data={"chat_id": chat_id, "text": chunk},
                )
        logger.info("performance_monitor.telegram_sent", chat_id=chat_id)

    async def _save_to_brain(self, analysis: dict, report: str, tenant_id: str) -> None:
        try:
            from app.core import brain
            brain.append(
                "monitor/history",
                {
                    "generated_at": datetime.utcnow().isoformat(),
                    "alerts": len(analysis["alerts"]),
                    "opportunities": len(analysis["opportunities"]),
                    "critical": analysis["critical"],
                    "report_snippet": report[:300],
                },
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning("performance_monitor.brain_save_failed", error=str(e))
