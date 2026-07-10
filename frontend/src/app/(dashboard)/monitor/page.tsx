"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, TrendingUp, TrendingDown, Play, RefreshCw,
  CheckCircle2, XCircle, Clock, Zap, BarChart2, Bell, BellOff,
  ChevronDown, ChevronUp, Activity,
} from "lucide-react";
import { clsx } from "clsx";
import { toast } from "sonner";
import { useApi } from "@/hooks/useApi";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Alert {
  severity: "critical" | "warning";
  adset: string;
  metric: string;
  value: number;
  threshold: number;
  action: string;
  spend_7d: number;
}

interface Opportunity {
  adset: string;
  type: string;
  metric: string;
  value: number;
  action: string;
  spend_7d: number;
}

interface Winner {
  adset: string;
  roas?: number;
  cpa?: number;
}

interface MonitorResult {
  status: "ok" | "skipped";
  reason?: string;
  alerts: number;
  opportunities: number;
  critical: boolean;
  report?: string;
  alerts_data?: Alert[];
  opportunities_data?: Opportunity[];
  winners?: Winner[];
  total_spend_7d?: number;
  generated_at?: string;
}

interface HistoryItem {
  generated_at: string;
  alerts: number;
  opportunities: number;
  critical: boolean;
  spend_7d: number;
  report_snippet: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const NEXT_RUNS = ["00:50", "06:50", "12:50", "18:50"];

function nextRunIn(): string {
  const now = new Date();
  const nowMins = now.getHours() * 60 + now.getMinutes();
  const runMins = NEXT_RUNS.map((t) => {
    const [h, m] = t.split(":").map(Number);
    return h * 60 + m;
  });
  const next = runMins.find((m) => m > nowMins) ?? runMins[0] + 24 * 60;
  const diff = next - nowMins;
  const h = Math.floor(diff / 60);
  const m = diff % 60;
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

// ─── Alert Card ──────────────────────────────────────────────────────────────

function AlertCard({ alert }: { alert: Alert }) {
  const isCritical = alert.severity === "critical";
  return (
    <div
      className={clsx(
        "rounded-xl border p-4 space-y-2",
        isCritical
          ? "bg-red-500/5 border-red-500/20"
          : "bg-yellow-500/5 border-yellow-500/20"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {isCritical ? (
            <XCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
          ) : (
            <AlertTriangle size={16} className="text-yellow-400 shrink-0 mt-0.5" />
          )}
          <span className="text-sm font-medium text-white truncate max-w-[260px]">
            {alert.adset}
          </span>
        </div>
        <span
          className={clsx(
            "text-[10px] font-mono px-2 py-0.5 rounded-full shrink-0",
            isCritical
              ? "bg-red-500/20 text-red-400"
              : "bg-yellow-500/20 text-yellow-400"
          )}
        >
          {isCritical ? "CRÍTICO" : "ATENÇÃO"}
        </span>
      </div>

      <div className="flex items-center gap-4 text-xs text-gray-400 pl-6">
        <span>
          <span className="text-gray-500">{alert.metric}:</span>{" "}
          <span className={isCritical ? "text-red-400 font-mono" : "text-yellow-400 font-mono"}>
            {typeof alert.value === "number" && alert.value < 10
              ? alert.value.toFixed(2)
              : alert.value}
          </span>
        </span>
        <span className="text-gray-600">gasto 7d: R${alert.spend_7d?.toFixed(0)}</span>
      </div>

      <p className="text-xs text-gray-300 pl-6">{alert.action}</p>
    </div>
  );
}

// ─── Opportunity Card ────────────────────────────────────────────────────────

function OpportunityCard({ opp }: { opp: Opportunity }) {
  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 space-y-2">
      <div className="flex items-center gap-2">
        <TrendingUp size={16} className="text-emerald-400 shrink-0" />
        <span className="text-sm font-medium text-white truncate max-w-[260px]">
          {opp.adset}
        </span>
        <span className="ml-auto text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full font-mono shrink-0">
          ESCALAR
        </span>
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-400 pl-6">
        <span>
          <span className="text-gray-500">{opp.metric}:</span>{" "}
          <span className="text-emerald-400 font-mono">
            {typeof opp.value === "number" && opp.value < 20
              ? opp.value.toFixed(2)
              : opp.value}
          </span>
        </span>
        <span className="text-gray-600">gasto 7d: R${opp.spend_7d?.toFixed(0)}</span>
      </div>
      <p className="text-xs text-gray-300 pl-6">{opp.action}</p>
    </div>
  );
}

// ─── History Row ─────────────────────────────────────────────────────────────

function HistoryRow({ item }: { item: HistoryItem }) {
  const [open, setOpen] = useState(false);
  const date = new Date(item.generated_at);

  return (
    <div className="border-b border-surface-border last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 py-3 px-4 hover:bg-surface-border/30 transition-colors text-left"
      >
        <span className="text-xs text-gray-500 w-28 shrink-0 font-mono">
          {date.toLocaleDateString("pt-BR")} {date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
        </span>

        <div className="flex items-center gap-2 flex-1">
          {item.critical ? (
            <span className="text-[10px] bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">Crítico</span>
          ) : item.alerts > 0 ? (
            <span className="text-[10px] bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded-full">
              {item.alerts} alerta{item.alerts > 1 ? "s" : ""}
            </span>
          ) : (
            <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full">OK</span>
          )}

          {item.opportunities > 0 && (
            <span className="text-[10px] bg-brand-500/20 text-brand-400 px-2 py-0.5 rounded-full">
              {item.opportunities} oportunidade{item.opportunities > 1 ? "s" : ""}
            </span>
          )}
        </div>

        <span className="text-xs text-gray-600 font-mono shrink-0">
          R${item.spend_7d?.toFixed(0)}
        </span>

        {open ? (
          <ChevronUp size={14} className="text-gray-600 shrink-0" />
        ) : (
          <ChevronDown size={14} className="text-gray-600 shrink-0" />
        )}
      </button>

      {open && item.report_snippet && (
        <div className="px-4 pb-3">
          <p className="text-xs text-gray-400 bg-surface-border/40 rounded-lg p-3 leading-relaxed">
            {item.report_snippet}
            {item.report_snippet.length >= 200 && "…"}
          </p>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function MonitorPage() {
  const api = useApi();
  const qc = useQueryClient();
  const [lastResult, setLastResult] = useState<MonitorResult | null>(null);

  const historyQ = useQuery<{ history: HistoryItem[] }>({
    queryKey: ["monitor-history"],
    queryFn: () => api.get("/monitor/history").then((r) => r.data),
    refetchInterval: 60_000,
  });

  const runMut = useMutation({
    mutationFn: () => api.post("/monitor/run"),
    onSuccess: (res) => {
      setLastResult(res.data);
      qc.invalidateQueries({ queryKey: ["monitor-history"] });
      if (res.data.critical) {
        toast.error("Análise concluída — alertas críticos encontrados!");
      } else if (res.data.alerts > 0) {
        toast.warning(`Análise concluída — ${res.data.alerts} alerta(s) encontrado(s).`);
      } else {
        toast.success("Análise concluída — tudo dentro do esperado.");
      }
    },
    onError: () => toast.error("Erro ao executar análise."),
  });

  const history = historyQ.data?.history ?? [];
  const lastHistory = history[0];

  // Summary stats from history
  const totalAlerts = history.slice(0, 4).reduce((s, h) => s + h.alerts, 0);
  const hasCritical = history.slice(0, 1).some((h) => h.critical);
  const totalOpps = history.slice(0, 4).reduce((s, h) => s + h.opportunities, 0);

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Activity size={24} className="text-brand-400" />
            Monitor de Performance
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Análise automática 24h — Blaze · Circo do Tiru · MMABET · Donald Bet
          </p>
        </div>

        <button
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
          className="flex items-center gap-2 px-4 py-2.5 bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white rounded-xl text-sm font-medium transition-colors"
        >
          {runMut.isPending ? (
            <RefreshCw size={16} className="animate-spin" />
          ) : (
            <Play size={16} />
          )}
          {runMut.isPending ? "Analisando…" : "Analisar Agora"}
        </button>
      </div>

      {/* Status bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <Clock size={14} className="text-gray-500" />
            <span className="text-xs text-gray-500">Próxima análise</span>
          </div>
          <p className="text-lg font-bold text-white">{nextRunIn()}</p>
          <p className="text-[10px] text-gray-600 mt-0.5">00h · 06h · 12h · 18h</p>
        </div>

        <div
          className={clsx(
            "border rounded-xl p-4",
            hasCritical
              ? "bg-red-500/5 border-red-500/20"
              : "bg-surface-card border-surface-border"
          )}
        >
          <div className="flex items-center gap-2 mb-1">
            <Bell size={14} className={hasCritical ? "text-red-400" : "text-gray-500"} />
            <span className="text-xs text-gray-500">Alertas (24h)</span>
          </div>
          <p className={clsx("text-lg font-bold", hasCritical ? "text-red-400" : "text-white")}>
            {totalAlerts}
          </p>
          <p className="text-[10px] text-gray-600 mt-0.5">
            {hasCritical ? "Ação necessária" : "Nas últimas 4 análises"}
          </p>
        </div>

        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp size={14} className="text-emerald-400" />
            <span className="text-xs text-gray-500">Oportunidades</span>
          </div>
          <p className="text-lg font-bold text-emerald-400">{totalOpps}</p>
          <p className="text-[10px] text-gray-600 mt-0.5">Para escalar</p>
        </div>

        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 size={14} className="text-brand-400" />
            <span className="text-xs text-gray-500">Status</span>
          </div>
          <p className="text-lg font-bold text-brand-400">Ativo</p>
          <p className="text-[10px] text-gray-600 mt-0.5">24h automático</p>
        </div>
      </div>

      {/* Resultado da última análise manual */}
      {runMut.isPending && (
        <div className="bg-surface-card border border-brand-500/20 rounded-xl p-6 text-center">
          <RefreshCw size={24} className="animate-spin text-brand-400 mx-auto mb-3" />
          <p className="text-sm text-gray-300">Buscando métricas e analisando campanhas…</p>
          <p className="text-xs text-gray-500 mt-1">Isso leva alguns segundos</p>
        </div>
      )}

      {lastResult && !runMut.isPending && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Resultado da Análise
          </h2>

          {/* Relatório IA */}
          {lastResult.report && (
            <div className="bg-surface-card border border-surface-border rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <Zap size={14} className="text-brand-400" />
                <span className="text-xs font-medium text-brand-400">Análise por IA</span>
              </div>
              <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                {lastResult.report}
              </p>
            </div>
          )}

          {/* Alertas */}
          {lastResult.alerts_data && lastResult.alerts_data.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Alertas ({lastResult.alerts_data.length})
              </h3>
              {lastResult.alerts_data.map((a, i) => (
                <AlertCard key={i} alert={a} />
              ))}
            </div>
          )}

          {/* Oportunidades */}
          {lastResult.opportunities_data && lastResult.opportunities_data.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Oportunidades ({lastResult.opportunities_data.length})
              </h3>
              {lastResult.opportunities_data.map((o, i) => (
                <OpportunityCard key={i} opp={o} />
              ))}
            </div>
          )}

          {lastResult.alerts === 0 && lastResult.opportunities === 0 && (
            <div className="flex items-center gap-3 bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4">
              <CheckCircle2 size={20} className="text-emerald-400 shrink-0" />
              <div>
                <p className="text-sm font-medium text-white">Tudo dentro do esperado</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  Nenhum alerta ou oportunidade identificada neste momento.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Histórico */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Histórico de Análises
        </h2>

        {historyQ.isLoading ? (
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 py-3 px-4 border-b border-surface-border last:border-0 animate-pulse">
                <div className="h-3 bg-gray-800 rounded w-24" />
                <div className="h-3 bg-gray-800 rounded w-16" />
                <div className="h-3 bg-gray-800 rounded w-20 ml-auto" />
              </div>
            ))}
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-surface-card border border-surface-border rounded-xl">
            <BarChart2 size={36} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">Nenhuma análise executada ainda.</p>
            <p className="text-xs mt-1">Clique em "Analisar Agora" para começar.</p>
          </div>
        ) : (
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            {history.map((item, i) => (
              <HistoryRow key={i} item={item} />
            ))}
          </div>
        )}
      </div>

      {/* Benchmarks configurados */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Benchmarks Configurados
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <p className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <TrendingUp size={13} className="text-brand-400" />
              Compra (Circo do Tiru · Zona de Jogo)
            </p>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">ROAS mínimo</span>
                <span className="text-white font-mono">3,0x</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">ROAS crítico</span>
                <span className="text-red-400 font-mono">&lt; 2,0x</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">CPA máximo</span>
                <span className="text-white font-mono">R$ 4,50</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Escalar se ROAS</span>
                <span className="text-emerald-400 font-mono">&gt; 5,0x</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Frequência máx</span>
                <span className="text-white font-mono">3,5</span>
              </div>
            </div>
          </div>

          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <p className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <Zap size={13} className="text-yellow-400" />
              Cadastro (MMABET · Donald Bet · Lance da Sorte)
            </p>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">CPL máximo</span>
                <span className="text-white font-mono">R$ 2,50</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">CPL crítico</span>
                <span className="text-red-400 font-mono">&gt; R$ 3,50</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Escalar se CPL</span>
                <span className="text-emerald-400 font-mono">&lt; R$ 1,20</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Frequência máx</span>
                <span className="text-white font-mono">4,0</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
