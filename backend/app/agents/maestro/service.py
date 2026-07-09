"""
Maestro — Orquestrador Principal
Regra fundamental: O Maestro NUNCA executa tarefas diretamente.
Ele analisa objetivos, decompõe em subtarefas, escolhe os agentes certos,
coordena execução em paralelo, valida entregas e gera relatório final.

Fluxo de uma requisição:
  1. Recebe objetivo em linguagem natural
  2. Consulta Brain (regras, playbooks, histórico do tenant)
  3. Claude decompõe em plano de execução (JSON)
  4. Executa agentes em paralelo por wave (dependências respeitadas)
  5. Valida entregáveis de cada wave
  6. Publica resultado na Knowledge Base
  7. Salva lições no Brain
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from app.agents.base import AgentBase
from app.core import brain
from app.core.logging import logger
from app.domain.events.base import DomainEvent, EventTypes
from app.domain.events.bus import publish


MAESTRO_SYSTEM_PROMPT = """Você é o Maestro — orquestrador de um sistema de IA para gestão de tráfego pago.

Seu único trabalho é PLANEJAR, nunca executar.

Dado um objetivo, você deve:
1. Decompor em subtarefas atômicas
2. Identificar dependências entre tarefas
3. Agrupar em waves paralelas (tarefas sem dependência rodam em paralelo)
4. Escolher qual agente executa cada tarefa
5. Definir critérios de sucesso para cada entregável

AGENTES DISPONÍVEIS:
- scanner: coleta dados brutos do Meta API
- analyst: analisa métricas e tendências
- doctor: diagnóstico de problemas em campanhas
- decision: toma decisões de otimização
- creative: analisa e recomenda criativos
- budget_optimizer: redistribui orçamentos
- copy: gera copy para anúncios
- compliance: valida contra políticas de plataforma
- pixel: verifica tracking e conversões
- audience_optimizer: otimiza segmentações
- learning: extrai e persiste lições
- reporting: gera relatórios
- whatsapp: envia comunicações

Responda SEMPRE em JSON válido:
{
  "objective_parsed": "interpretação do objetivo",
  "waves": [
    {
      "wave": 1,
      "parallel": true,
      "tasks": [
        {
          "task_id": "t1",
          "agent": "nome_do_agente",
          "action": "método a chamar (ex: run, scan_account)",
          "input": {"chave": "valor específico"},
          "depends_on": [],
          "success_criteria": "o que deve estar presente no resultado",
          "is_critical": true
        }
      ]
    }
  ],
  "estimated_duration_minutes": 5,
  "requires_human_approval": false,
  "approval_reason": null
}"""


class MaestroService(AgentBase):
    name = "maestro"

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    async def orchestrate(self, objective: str, tenant_id: str) -> dict[str, Any]:
        """Entry point: receive a natural language objective and coordinate agents."""
        self._tenant_id = tenant_id
        started_at = time.monotonic()

        logger.info("maestro.start", tenant_id=tenant_id, objective=objective[:100])

        # 1. Consult Brain for context
        context = self._build_context(tenant_id)

        # 2. Claude creates execution plan
        plan_raw = await self.ai_think(
            system_prompt=MAESTRO_SYSTEM_PROMPT,
            user_message=f"""OBJETIVO DO USUÁRIO:
{objective}

CONTEXTO DO TENANT:
{json.dumps(context, ensure_ascii=False, indent=2)}

Crie o plano de execução completo em JSON.""",
            max_tokens=2000,
        )

        plan = self._parse_plan(plan_raw)
        plan["objective"] = objective
        plan["tenant_id"] = tenant_id
        plan["started_at"] = datetime.utcnow().isoformat()

        logger.info(
            "maestro.plan_created",
            waves=len(plan.get("waves", [])),
            requires_approval=plan.get("requires_human_approval"),
        )

        # 3. If plan requires approval, save and return for human review
        if plan.get("requires_human_approval"):
            await self._save_pending_plan(plan, tenant_id)
            return {
                "status": "awaiting_approval",
                "plan": plan,
                "message": plan.get("approval_reason", "Aprovação humana necessária."),
            }

        # 4. Execute waves
        results = await self._execute_waves(plan, tenant_id)

        # 5. Build final report
        duration_s = time.monotonic() - started_at
        report = await self._build_report(objective, plan, results, duration_s)

        # 6. Save orchestration to Brain history
        brain.save_client_event(tenant_id, {
            "type": "maestro_orchestration",
            "objective": objective,
            "waves": len(plan.get("waves", [])),
            "tasks_total": sum(len(w["tasks"]) for w in plan.get("waves", [])),
            "tasks_ok": sum(1 for r in results.values() if r.get("ok")),
            "duration_s": round(duration_s, 1),
        })

        # 7. Publish orchestration completed event
        await publish(DomainEvent(
            event_type="maestro.orchestration_completed",
            tenant_id=tenant_id,
            payload={"objective": objective[:200], "tasks": len(results)},
        ))

        return report

    async def resume_plan(self, plan: dict, tenant_id: str) -> dict[str, Any]:
        """Execute a previously saved plan after human approval."""
        self._tenant_id = tenant_id
        started_at = time.monotonic()
        results = await self._execute_waves(plan, tenant_id)
        duration_s = time.monotonic() - started_at
        return await self._build_report(plan["objective"], plan, results, duration_s)

    # -------------------------------------------------------------------------
    # Wave execution
    # -------------------------------------------------------------------------

    async def _execute_waves(self, plan: dict, tenant_id: str) -> dict[str, Any]:
        all_results: dict[str, Any] = {}

        for wave in plan.get("waves", []):
            wave_num = wave.get("wave", "?")
            tasks = wave.get("tasks", [])
            logger.info("maestro.wave_start", wave=wave_num, tasks=len(tasks))

            if wave.get("parallel", True):
                coros = [self._run_task(t, tenant_id, all_results) for t in tasks]
                wave_results = await asyncio.gather(*coros, return_exceptions=True)
                for task, result in zip(tasks, wave_results):
                    tid = task["task_id"]
                    if isinstance(result, Exception):
                        all_results[tid] = {"ok": False, "error": str(result)}
                        logger.error("maestro.task_failed", task_id=tid, error=str(result))
                        if task.get("is_critical"):
                            logger.warning("maestro.critical_task_failed_stopping", task_id=tid)
                            return all_results
                    else:
                        all_results[tid] = result
            else:
                for task in tasks:
                    tid = task["task_id"]
                    try:
                        all_results[tid] = await self._run_task(task, tenant_id, all_results)
                    except Exception as exc:
                        all_results[tid] = {"ok": False, "error": str(exc)}
                        if task.get("is_critical"):
                            return all_results

            logger.info("maestro.wave_done", wave=wave_num)

        return all_results

    async def _run_task(self, task: dict, tenant_id: str, prev_results: dict) -> dict:
        """Instantiate the right agent and call the right method."""
        agent_name = task.get("agent", "")
        action = task.get("action", "run")
        task_input = task.get("input", {})

        # Merge outputs from dependencies into input
        for dep_id in task.get("depends_on", []):
            dep_result = prev_results.get(dep_id, {})
            if dep_result.get("ok"):
                task_input[f"_dep_{dep_id}"] = dep_result.get("data")

        svc = self._load_agent(agent_name, tenant_id)
        if svc is None:
            return {"ok": False, "error": f"Agent '{agent_name}' not found"}

        try:
            method = getattr(svc, action)
            if action == "run":
                data = await method(tenant_id)
            else:
                data = await method(**task_input)
            return {"ok": True, "agent": agent_name, "task_id": task["task_id"], "data": data}
        except Exception as exc:
            logger.error("maestro.task_error", agent=agent_name, action=action, error=str(exc))
            return {"ok": False, "agent": agent_name, "error": str(exc)}

    def _load_agent(self, agent_name: str, tenant_id: str):
        """Dynamic agent instantiation — avoids circular imports."""
        registry = {
            "scanner":          ("app.agents.scanner.service", "ScannerService"),
            "analyst":          ("app.agents.analyst.service", "AnalystService"),
            "doctor":           ("app.agents.doctor.service", "DoctorService"),
            "decision":         ("app.agents.decision.service", "DecisionService"),
            "creative":         ("app.agents.creative.service", "CreativeService"),
            "budget_optimizer": ("app.agents.budget_optimizer.service", "BudgetOptimizerService"),
            "whatsapp":         ("app.agents.whatsapp.service", "WhatsAppService"),
            "learning":         ("app.agents.learning.service", "LearningService"),
            "simulation":       ("app.agents.simulation.service", "SimulationService"),
        }

        entry = registry.get(agent_name)
        if not entry:
            return None

        module_path, class_name = entry
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            return cls(self._s, tenant_id)
        except Exception as exc:
            logger.error("maestro.agent_load_failed", agent=agent_name, error=str(exc))
            return None

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _build_context(self, tenant_id: str) -> dict:
        return {
            "rules": brain.get_rules(tenant_id),
            "recent_history": brain.get_client_history(tenant_id, limit=10),
            "recent_lessons": brain.get_lessons("what_works", limit=5),
            "recent_failures": brain.get_lessons("what_fails", limit=5),
        }

    def _parse_plan(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {
            "objective_parsed": "Erro ao parsear plano",
            "waves": [],
            "requires_human_approval": False,
        }

    async def _save_pending_plan(self, plan: dict, tenant_id: str) -> None:
        await self.publish_knowledge(
            topic="pending_maestro_plan",
            entry_type="decision",
            content=plan,
            summary=f"Plano pendente de aprovação: {plan.get('objective', '')[:150]}",
            confidence=0.9,
            ttl_hours=48,
        )

    async def _build_report(
        self,
        objective: str,
        plan: dict,
        results: dict,
        duration_s: float,
    ) -> dict:
        ok_count = sum(1 for r in results.values() if r.get("ok"))
        fail_count = len(results) - ok_count
        errors = [
            {"task": tid, "error": r["error"]}
            for tid, r in results.items() if not r.get("ok")
        ]

        report_text = await self.ai_think(
            system_prompt="Você é o Maestro. Gere um relatório executivo conciso em português sobre a orquestração concluída.",
            user_message=f"""Objetivo: {objective}

Tarefas executadas: {len(results)} | Sucesso: {ok_count} | Falhas: {fail_count}
Duração: {duration_s:.1f}s

Erros (se houver): {json.dumps(errors, ensure_ascii=False)}

Escreva um parágrafo resumindo o que foi feito e o resultado.""",
            max_tokens=400,
        )

        final = {
            "status": "completed" if fail_count == 0 else "completed_with_errors",
            "objective": objective,
            "plan_summary": plan.get("objective_parsed", ""),
            "tasks_total": len(results),
            "tasks_ok": ok_count,
            "tasks_failed": fail_count,
            "duration_seconds": round(duration_s, 1),
            "errors": errors,
            "report": report_text,
            "completed_at": datetime.utcnow().isoformat(),
        }

        await self.publish_knowledge(
            topic="maestro_report",
            entry_type="report",
            content=final,
            summary=report_text[:400],
            confidence=1.0,
            ttl_hours=72,
        )

        logger.info(
            "maestro.done",
            ok=ok_count,
            failed=fail_count,
            duration=round(duration_s, 1),
        )
        return final
