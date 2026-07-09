"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import type { ReportSummary, Diagnosis, AgentAction } from "@/types";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";

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

  const fmt = (n?: number, prefix = "") =>
    n !== undefined ? `${prefix}${n.toLocaleString("pt-BR")}` : "—";

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <p className="text-gray-400 text-sm mt-1">Visão geral dos últimos 7 dias</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <StatCard label="Gasto" value={fmt(summary?.spend, "R$ ")} />
        <StatCard label="Conversões" value={fmt(summary?.conversions)} />
        <StatCard label="ROAS" value={summary?.roas ? `${summary.roas.toFixed(2)}x` : "—"} trend={summary?.roas && summary.roas >= 1 ? "up" : "down"} />
        <StatCard label="CPA" value={fmt(summary?.cpa, "R$ ")} />
        <StatCard label="CTR" value={summary?.ctr ? `${summary.ctr.toFixed(2)}%` : "—"} />
        <StatCard label="CPM" value={fmt(summary?.cpm, "R$ ")} />
        <StatCard label="Cliques" value={fmt(summary?.clicks)} />
        <StatCard label="Impressões" value={fmt(summary?.impressions)} />
        <StatCard label="Alertas" value={diagnoses?.length ?? 0} trend={diagnoses?.length ? "down" : "up"} />
        <StatCard label="Ações" value={actions?.length ?? 0} />
      </div>

      {/* Timeline chart */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Gasto e Conversões (30 dias)</h3>
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
            />
            <Area type="monotone" dataKey="spend" stroke="#1d6fee" fill="url(#spend)" name="Gasto (R$)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Alerts */}
      {diagnoses && diagnoses.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Alertas Ativos</h3>
          <div className="space-y-2">
            {diagnoses.slice(0, 10).map((d) => (
              <div key={d.id} className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
                <div>
                  <span className={`badge-${d.severity} mr-2`}>{d.severity.toUpperCase()}</span>
                  <span className="text-sm text-gray-300">{d.issue_type}</span>
                  <span className="text-xs text-gray-500 ml-2">{d.entity_id}</span>
                </div>
                <span className="text-xs text-gray-500">
                  {new Date(d.created_at).toLocaleDateString("pt-BR")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
