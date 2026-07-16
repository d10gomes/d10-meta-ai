"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import { translateIssue } from "@/lib/labels";
import type { ReportSummary, Diagnosis, AgentAction } from "@/types";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar, Legend,
} from "recharts";

// ── Períodos igual ao Meta Ads Manager ────────────────────────────────────────

const PERIODS = [
  { label: "Hoje",     days: 1,   preset: "today" },
  { label: "Ontem",    days: 2,   preset: "yesterday" },
  { label: "7 dias",   days: 7,   preset: "last_7d" },
  { label: "14 dias",  days: 14,  preset: "last_14d" },
  { label: "30 dias",  days: 30,  preset: "last_30d" },
  { label: "3 meses",  days: 90,  preset: "last_90d" },
] as const;

type Period = typeof PERIODS[number];

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtBRL = (n?: number) =>
  n != null
    ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n)
    : "—";

const fmtNum = (n?: number) =>
  n != null ? new Intl.NumberFormat("pt-BR").format(n) : "—";

const SEVERITY_ICON: Record<string, string> = { critical: "🔴", high: "🟠", medium: "🟡", low: "🟢" };
const SEVERITY_LABEL: Record<string, string> = { critical: "Crítico", high: "Alto", medium: "Atenção", low: "Baixo" };

// ── Componente principal ──────────────────────────────────────────────────────

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>(PERIODS[2]); // 7 dias default
  const [chartMetric, setChartMetric] = useState<"spend" | "roas" | "conversions">("spend");

  const { data: summary, isLoading: loadingKPIs } = useQuery<ReportSummary>({
    queryKey: ["summary", period.days],
    queryFn: () => api.get(`/reports/summary?days=${period.days}`).then((r) => r.data),
  });

  const { data: timeline, isLoading: loadingChart } = useQuery<{ day: string; spend: number; roas: number; conversions: number }[]>({
    queryKey: ["timeline", period.days],
    queryFn: () => api.get(`/reports/timeline?days=${period.days}`).then((r) => r.data),
  });

  const { data: diagnoses } = useQuery<Diagnosis[]>({
    queryKey: ["diagnoses"],
    queryFn: () => api.get("/diagnoses").then((r) => r.data),
  });

  const { data: actions } = useQuery<AgentAction[]>({
    queryKey: ["actions"],
    queryFn: () => api.get("/actions").then((r) => r.data),
  });

  const criticalIssues = diagnoses?.filter((d) => d.severity === "critical" || d.severity === "high") ?? [];

  // Formata label do eixo X conforme o período
  const fmtDay = (iso: string) => {
    const d = new Date(iso + "T00:00:00");
    if (period.days <= 2) return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    if (period.days <= 14) return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit" });
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
  };

  const chartData = (timeline ?? []).map((r) => ({ ...r, day: fmtDay(r.day) }));

  const CHART_METRICS = [
    { key: "spend",       label: "Gasto (R$)",   color: "#1d6fee", fmt: (v: number) => fmtBRL(v) },
    { key: "roas",        label: "ROAS",          color: "#10b981", fmt: (v: number) => `${v.toFixed(2)}x` },
    { key: "conversions", label: "Conversões",    color: "#f59e0b", fmt: (v: number) => fmtNum(v) },
  ] as const;

  const activeMetric = CHART_METRICS.find((m) => m.key === chartMetric)!;

  return (
    <div className="space-y-6">
      {/* Header + seletor de período */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold">Visão Geral</h2>
          <p className="text-gray-400 text-sm mt-1">
            {period.label === "Hoje" || period.label === "Ontem"
              ? `Resultados de ${period.label.toLowerCase()}`
              : `Resultados dos últimos ${period.label}`}
          </p>
        </div>

        {/* Period tabs — igual ao Meta */}
        <div className="flex gap-1 bg-surface-card border border-surface-border rounded-xl p-1">
          {PERIODS.map((p) => (
            <button
              key={p.preset}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                period.preset === p.preset
                  ? "bg-brand-500 text-white shadow"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Alert banner */}
      {criticalIssues.length > 0 && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-start gap-3">
          <span className="text-2xl">🔴</span>
          <div>
            <p className="font-semibold text-red-300">
              {criticalIssues.length} problema{criticalIssues.length > 1 ? "s" : ""} crítico{criticalIssues.length > 1 ? "s" : ""} detectado{criticalIssues.length > 1 ? "s" : ""}
            </p>
            <p className="text-sm text-red-400/80 mt-0.5">
              Acesse <strong>Diagnósticos</strong> para ver detalhes e recomendações.
            </p>
          </div>
        </div>
      )}

      {/* KPI grid */}
      <div className={`grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4 transition-opacity ${loadingKPIs ? "opacity-50" : ""}`}>
        <StatCard label="Gasto total"          value={fmtBRL(summary?.spend)} />
        <StatCard label="Receita gerada"       value={fmtBRL(summary?.revenue)} trend={summary?.roas && summary.roas >= 1 ? "up" : "down"} />
        <StatCard label="ROAS"                 value={summary?.roas ? `${summary.roas.toFixed(2)}x` : "—"} trend={summary?.roas && summary.roas >= 1 ? "up" : "down"} />
        <StatCard label="Custo por cliente"    value={summary?.cpa ? fmtBRL(summary.cpa) : "—"} />
        <StatCard label="Conversões"           value={fmtNum(summary?.conversions)} />
        <StatCard label="Cliques"              value={fmtNum(summary?.clicks)} />
        <StatCard label="CTR"                  value={summary?.ctr ? `${summary.ctr.toFixed(2)}%` : "—"} />
        <StatCard label="CPM"                  value={summary?.cpm ? fmtBRL(summary.cpm) : "—"} />
        <StatCard label="Frequência média"     value={summary?.frequency ? `${summary.frequency.toFixed(1)}x` : "—"} />
        <StatCard label="Alertas ativos"       value={diagnoses?.length ?? 0} trend={diagnoses?.length ? "down" : "up"} />
      </div>

      {/* Gráfico */}
      <div className="card">
        {/* Cabeçalho do gráfico */}
        <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
          <div>
            <h3 className="text-base font-semibold text-white">{activeMetric.label} por dia</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {period.label === "Hoje" ? "Hoje" : period.label === "Ontem" ? "Ontem" : `Últimos ${period.label}`}
            </p>
          </div>
          {/* Seletor de métrica */}
          <div className="flex gap-1 bg-surface border border-surface-border rounded-lg p-1">
            {CHART_METRICS.map((m) => (
              <button
                key={m.key}
                onClick={() => setChartMetric(m.key)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  chartMetric === m.key
                    ? "text-white"
                    : "text-gray-500 hover:text-gray-300"
                }`}
                style={chartMetric === m.key ? { backgroundColor: m.color + "33", color: m.color } : {}}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {loadingChart ? (
          <div className="h-64 flex items-center justify-center text-gray-600 text-sm">Carregando...</div>
        ) : chartData.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-gray-600 text-sm">
            Sem dados para o período selecionado
          </div>
        ) : period.days <= 14 ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} barSize={period.days <= 2 ? 24 : 14}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
              <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} width={50} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#9ca3af" }}
                formatter={(v: number) => [activeMetric.fmt(v), activeMetric.label]}
              />
              <Bar dataKey={chartMetric} fill={activeMetric.color} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="gradMetric" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={activeMetric.color} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={activeMetric.color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
              <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} width={50} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#9ca3af" }}
                formatter={(v: number) => [activeMetric.fmt(v), activeMetric.label]}
              />
              <Area
                type="monotone"
                dataKey={chartMetric}
                stroke={activeMetric.color}
                strokeWidth={2}
                fill="url(#gradMetric)"
                dot={false}
                activeDot={{ r: 4, fill: activeMetric.color }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Diagnósticos */}
      {diagnoses && diagnoses.length > 0 && (
        <div className="card">
          <h3 className="text-base font-semibold mb-4">Problemas detectados</h3>
          <div className="space-y-0">
            {diagnoses.slice(0, 10).map((d) => (
              <div
                key={d.id}
                className="flex items-center justify-between py-2.5 border-b border-surface-border last:border-0"
              >
                <div className="flex items-center gap-3">
                  <span>{SEVERITY_ICON[d.severity] || "🟡"}</span>
                  <div>
                    <span className="text-sm text-white">{translateIssue(d.issue_type)}</span>
                    <p className="text-xs text-gray-500 mt-0.5">{SEVERITY_LABEL[d.severity] || d.severity}</p>
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
