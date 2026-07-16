"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import { translateIssue } from "@/lib/labels";
import type { ReportSummary, Diagnosis, AgentAction } from "@/types";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";

const SEVERITY_ICON: Record<string, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🟢",
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Atenção",
  low: "Baixo",
};

export default function DashboardPage() {
  const { data: summary } = useQuery<ReportSummary>({
    queryKey: ["summary"],
    queryFn: () => api.get("/reports/summary?days=7").then((r) => r.data),
  });

  const { data: timeline } = useQuery({
    queryKey: ["timeline"],
    queryFn: () => api.get("/reports/timeline?days=30").then((r) => r.data),
  });

  const { data: diagnoses } = useQuery<Diagnosis[]>({
    queryKey: ["diagnoses"],
    queryFn: () => api.get("/diagnoses").then((r) => r.data),
  });

  const { data: actions } = useQuery<AgentAction[]>({
    queryKey: ["actions"],
    queryFn: () => api.get("/actions").then((r) => r.data),
  });

  const fmtBRL = (n?: number) =>
    n !== undefined
      ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n)
      : "—";

  const fmtNum = (n?: number) =>
    n !== undefined ? new Intl.NumberFormat("pt-BR").format(n) : "—";

  const criticalIssues = diagnoses?.filter((d) => d.severity === "critical" || d.severity === "high") ?? [];

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Visão Geral</h2>
        <p className="text-gray-400 text-sm mt-1">Resultados dos últimos 7 dias</p>
      </div>

      {/* Alert banner for critical issues */}
      {criticalIssues.length > 0 && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-start gap-3">
          <span className="text-2xl">🔴</span>
          <div>
            <p className="font-semibold text-red-300">
              {criticalIssues.length} problema{criticalIssues.length > 1 ? "s" : ""} crítico{criticalIssues.length > 1 ? "s" : ""} detectado{criticalIssues.length > 1 ? "s" : ""}
            </p>
            <p className="text-sm text-red-400/80 mt-0.5">
              Acesse <strong>Diagnósticos</strong> para ver detalhes e recomendações de ação.
            </p>
          </div>
        </div>
      )}

      {/* KPIs in plain language */}
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <StatCard
          label="Quanto foi gasto"
          value={fmtBRL(summary?.spend)}
        />
        <StatCard
          label="Quanto trouxe de volta"
          value={fmtBRL(summary?.revenue)}
          trend={summary?.roas && summary.roas >= 1 ? "up" : "down"}
        />
        <StatCard
          label="Retorno por R$ 1 gasto"
          value={summary?.roas ? `${summary.roas.toFixed(2)}x` : "—"}
          trend={summary?.roas && summary.roas >= 1 ? "up" : "down"}
        />
        <StatCard
          label="Custo por cliente"
          value={summary?.cpa ? fmtBRL(summary.cpa) : "—"}
        />
        <StatCard
          label="Clientes conquistados"
          value={fmtNum(summary?.conversions)}
        />
        <StatCard
          label="Pessoas que clicaram"
          value={fmtNum(summary?.clicks)}
        />
        <StatCard
          label="Taxa de cliques"
          value={summary?.ctr ? `${summary.ctr.toFixed(2)}%` : "—"}
        />
        <StatCard
          label="Custo por 1.000 visualizações"
          value={summary?.cpm ? fmtBRL(summary.cpm) : "—"}
        />
        <StatCard
          label="Alertas ativos"
          value={diagnoses?.length ?? 0}
          trend={diagnoses?.length ? "down" : "up"}
        />
        <StatCard
          label="Ações do mês"
          value={actions?.length ?? 0}
        />
      </div>

      {/* Chart */}
      <div className="card">
        <div className="mb-4">
          <h3 className="text-lg font-semibold">Quanto foi gasto por dia (últimos 30 dias)</h3>
          <p className="text-xs text-gray-500 mt-1">
            Passe o mouse sobre o gráfico para ver o valor exato de cada dia
          </p>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={timeline || []}>
            <defs>
              <linearGradient id="spend" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#1d6fee" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#1d6fee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
            <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 11 }} />
            <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8 }}
              labelStyle={{ color: "#9ca3af" }}
              formatter={(v: number) => [`R$ ${v.toLocaleString("pt-BR")}`, "Gasto"]}
            />
            <Area type="monotone" dataKey="spend" stroke="#1d6fee" fill="url(#spend)" name="Gasto (R$)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Alerts in plain language */}
      {diagnoses && diagnoses.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Problemas detectados nas campanhas</h3>
          <div className="space-y-2">
            {diagnoses.slice(0, 10).map((d) => (
              <div
                key={d.id}
                className="flex items-center justify-between py-2.5 border-b border-surface-border last:border-0"
              >
                <div className="flex items-center gap-3">
                  <span className="text-base">{SEVERITY_ICON[d.severity] || "🟡"}</span>
                  <div>
                    <span className="text-sm text-white">{translateIssue(d.issue_type)}</span>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {SEVERITY_LABEL[d.severity] || d.severity}
                    </p>
                  </div>
                </div>
                <span className="text-xs text-gray-500 whitespace-nowrap ml-4">
                  {new Date(d.created_at).toLocaleDateString("pt-BR")}
                </span>
              </div>
            ))}
          </div>
          {diagnoses.length > 10 && (
            <p className="text-xs text-gray-500 mt-3 text-center">
              + {diagnoses.length - 10} outros — veja todos em <strong>Diagnósticos</strong>
            </p>
          )}
        </div>
      )}

      {diagnoses?.length === 0 && (
        <div className="card border border-green-500/20 bg-green-500/5 text-center py-6">
          <span className="text-3xl">✅</span>
          <p className="text-green-400 font-semibold mt-2">Tudo certo por enquanto!</p>
          <p className="text-sm text-gray-500 mt-1">Nenhum problema detectado nas suas campanhas.</p>
        </div>
      )}
    </div>
  );
}
