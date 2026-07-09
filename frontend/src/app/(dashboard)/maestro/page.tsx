"use client";
import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  Send, Loader2, CheckCircle2, XCircle, AlertTriangle,
  ChevronDown, ChevronUp, Zap, Clock, Brain, Sparkles,
} from "lucide-react";

type OrchestrationResult = {
  status: "completed" | "completed_with_errors" | "awaiting_approval";
  objective: string;
  plan_summary: string;
  tasks_total: number;
  tasks_ok: number;
  tasks_failed: number;
  duration_seconds: number;
  errors: { task: string; error: string }[];
  report: string;
  completed_at: string;
  message?: string;
  plan?: unknown;
};

type PendingApproval = {
  id: string;
  action_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  simulation: {
    risk_level: string;
    can_proceed: boolean;
    impact_estimate: Record<string, number>;
    risk_factors: string[];
    recommendation: string;
    confidence: number;
  } | null;
  status: string;
  created_at: string;
};

const SUGGESTIONS = [
  "Analise todas as campanhas e diga o que está com problema",
  "Otimize os budgets das campanhas com base no ROAS dos últimos 7 dias",
  "Quais criativos estão fatigados e precisam ser substituídos?",
  "Gere um diagnóstico completo de saúde das campanhas",
  "Redistribua o budget priorizando as campanhas com melhor retorno",
];

function RiskBadge({ level }: { level: string }) {
  const map: Record<string, string> = {
    low:      "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
    medium:   "bg-amber-500/10 text-amber-400 border border-amber-500/20",
    high:     "bg-orange-500/10 text-orange-400 border border-orange-500/20",
    critical: "bg-red-500/10 text-red-400 border border-red-500/20",
  };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${map[level] ?? map.medium}`}>
      {level.toUpperCase()}
    </span>
  );
}

function ImpactRow({ label, value }: { label: string; value: number }) {
  const color = value > 0 ? "text-emerald-400" : value < 0 ? "text-red-400" : "text-gray-400";
  return (
    <div className="flex justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono font-medium ${color}`}>
        {value > 0 ? "+" : ""}{value.toFixed(1)}%
      </span>
    </div>
  );
}

export default function MaestroPage() {
  const [input, setInput] = useState("");
  const [expandedApproval, setExpandedApproval] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<OrchestrationResult | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const qc = useQueryClient();

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = textareaRef.current.scrollHeight + "px";
    }
  }, [input]);

  const orchestrate = useMutation({
    mutationFn: (objective: string) =>
      api.post("/maestro/orchestrate", { objective }).then((r) => r.data),
    onSuccess: (data: OrchestrationResult) => {
      setLastResult(data);
      setInput("");
      qc.invalidateQueries({ queryKey: ["pending-approvals"] });
    },
    onError: () => showToast("Erro ao enviar para o Maestro.", "err"),
  });

  const approve = useMutation({
    mutationFn: (action_id: string) =>
      api.post("/maestro/approve", { action_id }).then((r) => r.data),
    onSuccess: () => {
      showToast("Ação aprovada! O Executor vai processar em breve.");
      qc.invalidateQueries({ queryKey: ["pending-approvals"] });
    },
    onError: () => showToast("Erro ao aprovar.", "err"),
  });

  const reject = useMutation({
    mutationFn: (action_id: string) =>
      api.post("/maestro/reject", { action_id, reason: "Rejeitado manualmente" }).then((r) => r.data),
    onSuccess: () => {
      showToast("Ação rejeitada.");
      qc.invalidateQueries({ queryKey: ["pending-approvals"] });
    },
    onError: () => showToast("Erro ao rejeitar.", "err"),
  });

  const { data: pendingData } = useQuery({
    queryKey: ["pending-approvals"],
    queryFn: () => api.get("/maestro/pending-approvals").then((r) => r.data),
    refetchInterval: 15000,
  });

  const pending: PendingApproval[] = pendingData ?? [];

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || orchestrate.isPending) return;
    orchestrate.mutate(input.trim());
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-5 py-3 rounded-lg shadow-lg text-sm text-white ${
          toast.type === "ok" ? "bg-green-600" : "bg-red-600"
        }`}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="bg-brand-500/10 p-3 rounded-xl text-brand-400 flex-shrink-0">
          <Brain size={28} />
        </div>
        <div>
          <h2 className="text-2xl font-bold">Maestro</h2>
          <p className="text-gray-400 text-sm mt-1">
            Descreva qualquer objetivo em linguagem natural. O Maestro analisa, planeja e coordena os agentes automaticamente.
          </p>
        </div>
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="card border border-gray-700 space-y-3">
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ex: Analise as campanhas e pause as que estão com ROAS abaixo de 1.0 há mais de 48h..."
            rows={2}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-brand-500 transition-colors pr-12"
            disabled={orchestrate.isPending}
          />
          <button
            type="submit"
            disabled={!input.trim() || orchestrate.isPending}
            className="absolute right-3 bottom-3 bg-brand-500 hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed text-white p-1.5 rounded-md transition-colors"
          >
            {orchestrate.isPending
              ? <Loader2 size={16} className="animate-spin" />
              : <Send size={16} />
            }
          </button>
        </div>
        <p className="text-xs text-gray-600">Enter para enviar · Shift+Enter para nova linha</p>

        {/* Suggestions */}
        <div className="flex gap-2 flex-wrap">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setInput(s)}
              disabled={orchestrate.isPending}
              className="text-xs text-gray-500 hover:text-brand-400 border border-gray-700 hover:border-brand-500/50 px-2.5 py-1 rounded-full transition-colors"
            >
              {s.length > 45 ? s.slice(0, 42) + "…" : s}
            </button>
          ))}
        </div>
      </form>

      {/* Running indicator */}
      {orchestrate.isPending && (
        <div className="card border border-brand-500/30 bg-brand-500/5">
          <div className="flex items-center gap-3">
            <Sparkles size={18} className="text-brand-400 animate-pulse" />
            <div>
              <p className="text-sm font-medium text-white">Maestro trabalhando…</p>
              <p className="text-xs text-gray-400 mt-0.5">Consultando Brain, planejando waves, coordenando agentes em paralelo</p>
            </div>
          </div>
          <div className="mt-3 h-1 bg-gray-800 rounded-full overflow-hidden">
            <div className="h-full bg-brand-500 rounded-full animate-pulse w-3/4" />
          </div>
        </div>
      )}

      {/* Result */}
      {lastResult && !orchestrate.isPending && (
        <div className={`card border ${
          lastResult.status === "completed"
            ? "border-emerald-500/30 bg-emerald-500/5"
            : lastResult.status === "awaiting_approval"
            ? "border-amber-500/30 bg-amber-500/5"
            : "border-orange-500/30 bg-orange-500/5"
        }`}>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2">
              {lastResult.status === "completed" && <CheckCircle2 size={18} className="text-emerald-400 flex-shrink-0" />}
              {lastResult.status === "awaiting_approval" && <AlertTriangle size={18} className="text-amber-400 flex-shrink-0" />}
              {lastResult.status === "completed_with_errors" && <XCircle size={18} className="text-orange-400 flex-shrink-0" />}
              <div>
                <p className="text-sm font-semibold text-white">
                  {lastResult.status === "completed" && "Orquestração concluída"}
                  {lastResult.status === "awaiting_approval" && "Aguardando aprovação"}
                  {lastResult.status === "completed_with_errors" && "Concluído com erros"}
                </p>
                {lastResult.tasks_total > 0 && (
                  <p className="text-xs text-gray-400 mt-0.5">
                    {lastResult.tasks_ok}/{lastResult.tasks_total} tarefas · {lastResult.duration_seconds?.toFixed(1)}s
                  </p>
                )}
              </div>
            </div>
            {lastResult.tasks_total > 0 && (
              <div className="flex gap-3 text-xs flex-shrink-0">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 size={11} /> {lastResult.tasks_ok}
                </span>
                {lastResult.tasks_failed > 0 && (
                  <span className="flex items-center gap-1 text-red-400">
                    <XCircle size={11} /> {lastResult.tasks_failed}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Report */}
          {lastResult.report && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{lastResult.report}</p>
            </div>
          )}

          {lastResult.message && (
            <p className="mt-3 text-sm text-amber-300">{lastResult.message}</p>
          )}

          {/* Errors */}
          {lastResult.errors?.length > 0 && (
            <div className="mt-3 space-y-1">
              {lastResult.errors.map((e, i) => (
                <p key={i} className="text-xs text-red-400 bg-red-500/5 rounded px-2 py-1">
                  <span className="font-mono font-bold">{e.task}:</span> {e.error}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Pending Approvals */}
      {pending.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-400" />
            <h3 className="font-semibold text-white">
              Aguardando Aprovação
              <span className="ml-2 bg-amber-500/20 text-amber-400 text-xs font-medium px-2 py-0.5 rounded-full">
                {pending.length}
              </span>
            </h3>
          </div>

          {pending.map((action) => (
            <div key={action.id} className="card border border-amber-500/20 bg-amber-500/5">
              <div
                className="flex items-start justify-between cursor-pointer"
                onClick={() => setExpandedApproval(expandedApproval === action.id ? null : action.id)}
              >
                <div className="flex items-start gap-3">
                  <Zap size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-white font-mono">{action.action_type}</p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {action.entity_type} · {action.entity_id || "—"}
                    </p>
                    {action.simulation && (
                      <div className="flex items-center gap-2 mt-1.5">
                        <RiskBadge level={action.simulation.risk_level} />
                        <span className="text-xs text-gray-500">
                          Confiança: {(action.simulation.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Clock size={12} className="text-gray-600" />
                  <span className="text-xs text-gray-500">
                    {new Date(action.created_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  {expandedApproval === action.id
                    ? <ChevronUp size={14} className="text-gray-500" />
                    : <ChevronDown size={14} className="text-gray-500" />
                  }
                </div>
              </div>

              {/* Expanded simulation detail */}
              {expandedApproval === action.id && action.simulation && (
                <div className="mt-4 pt-4 border-t border-gray-700 space-y-4">
                  {/* Impact estimate */}
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Impacto estimado</p>
                    <div className="bg-gray-900 rounded-lg p-3 space-y-2">
                      {action.simulation.impact_estimate?.roas_change_pct !== undefined && (
                        <ImpactRow label="ROAS" value={action.simulation.impact_estimate.roas_change_pct} />
                      )}
                      {action.simulation.impact_estimate?.spend_change_pct !== undefined && (
                        <ImpactRow label="Gasto" value={action.simulation.impact_estimate.spend_change_pct} />
                      )}
                      {action.simulation.impact_estimate?.conversions_change_pct !== undefined && (
                        <ImpactRow label="Conversões" value={action.simulation.impact_estimate.conversions_change_pct} />
                      )}
                    </div>
                  </div>

                  {/* Risk factors */}
                  {action.simulation.risk_factors?.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Fatores de risco</p>
                      <ul className="space-y-1">
                        {action.simulation.risk_factors.map((f, i) => (
                          <li key={i} className="text-xs text-gray-400 flex items-start gap-1.5">
                            <span className="text-amber-400 mt-0.5">·</span> {f}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Recommendation */}
                  {action.simulation.recommendation && (
                    <div className="bg-gray-900 rounded-lg p-3">
                      <p className="text-xs text-gray-400 leading-relaxed">{action.simulation.recommendation}</p>
                    </div>
                  )}

                  {/* Payload preview */}
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Parâmetros da ação</p>
                    <pre className="text-xs text-gray-400 bg-gray-900 rounded-lg p-3 overflow-x-auto">
                      {JSON.stringify(action.payload, null, 2)}
                    </pre>
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-3 pt-1">
                    <button
                      onClick={() => approve.mutate(action.id)}
                      disabled={approve.isPending || reject.isPending}
                      className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                    >
                      {approve.isPending ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                      Aprovar e Executar
                    </button>
                    <button
                      onClick={() => reject.mutate(action.id)}
                      disabled={approve.isPending || reject.isPending}
                      className="flex-1 flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                    >
                      <XCircle size={14} />
                      Rejeitar
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Empty pending state */}
      {pending.length === 0 && !orchestrate.isPending && !lastResult && (
        <div className="card border border-dashed border-gray-700 text-center py-12">
          <Brain size={32} className="text-gray-700 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">Nenhuma aprovação pendente.</p>
          <p className="text-gray-600 text-xs mt-1">Digite um objetivo acima para o Maestro começar a trabalhar.</p>
        </div>
      )}
    </div>
  );
}
