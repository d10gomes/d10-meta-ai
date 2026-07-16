"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ReportSummary, TimelinePoint } from "@/types";
import StatCard from "@/components/ui/StatCard";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const PERIODS = [
  { label: "Hoje",    days: 1  },
  { label: "Ontem",   days: 2  },
  { label: "7 dias",  days: 7  },
  { label: "14 dias", days: 14 },
  { label: "30 dias", days: 30 },
  { label: "3 meses", days: 90 },
] as const;

const PERIOD_LABELS: Record<number, string> = {
  1:  "hoje",
  2:  "ontem",
  7:  "últimos 7 dias",
  14: "últimos 14 dias",
  30: "último mês",
  90: "últimos 3 meses",
};

function HealthSummary({ summary, days }: { summary?: ReportSummary; days: number }) {
  if (!summary) return null;

  const roas = summary.roas ?? 0;
  const cpa = summary.cpa ?? 0;
  const spend = summary.spend ?? 0;
  const revenue = summary.revenue ?? 0;
  const profit = revenue - spend;

  const roasOk = roas >= 2;
  const profitOk = profit > 0;

  return (
    <div className="card border border-surface-border">
      <h3 className="font-semibold text-white mb-3">Resumo em linguagem simples — {PERIOD_LABELS[days]}</h3>
      <div className="space-y-2 text-sm">
        <div className="flex items-start gap-2">
          <span>{profitOk ? "✅" : "⚠️"}</span>
          <p className="text-gray-300">
            Você gastou{" "}
            <strong className="text-white">
              {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(spend)}
            </strong>{" "}
            e teve um retorno de{" "}
            <strong className={profitOk ? "text-green-400" : "text-red-400"}>
              {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(revenue)}
            </strong>
            {profitOk
              ? ` — lucro de ${new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(profit)}.`
              : ` — prejuízo de ${new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Math.abs(profit))}.`}
          </p>
        </div>
        <div className="flex items-start gap-2">
          <span>{roasOk ? "✅" : "⚠️"}</span>
          <p className="text-gray-300">
            Para cada R$ 1,00 investido, você recebeu de volta{" "}
            <strong className={roasOk ? "text-green-400" : "text-yellow-400"}>
              R$ {roas.toFixed(2)}
            </strong>
            {roasOk ? " — retorno positivo." : " — abaixo do ideal (esperado: R$ 2,00+)."}
          </p>
        </div>
        {cpa > 0 && (
          <div className="flex items-start gap-2">
            <span>💡</span>
            <p className="text-gray-300">
              Cada cliente custou em média{" "}
              <strong className="text-white">
                {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(cpa)}
              </strong>
              . Compare com o seu ticket médio para saber se está valendo a pena.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const [days, setDays] = useState(30);

  const { data: summary } = useQuery<ReportSummary>({
    queryKey: ["summary", days],
    queryFn: () => api.get(`/reports/summary?days=${days}`).then((r) => r.data),
  });

  const { data: timeline } = useQuery<TimelinePoint[]>({
    queryKey: ["timeline", days],
    queryFn: () => api.get(`/reports/timeline?days=${days}`).then((r) => r.data),
  });

  const fmtBRL = (n: number) =>
    new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold">Relatórios</h2>
          <p className="text-gray-400 text-sm mt-1">Análise de performance das suas campanhas</p>
        </div>
        <div className="flex gap-1 bg-surface-card border border-surface-border rounded-xl p-1">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              onClick={() => setDays(p.days)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                days === p.days
                  ? "bg-brand-500 text-white shadow"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Plain-language summary */}
      <HealthSummary summary={summary} days={days} />

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Total gasto"
          value={fmtBRL(summary?.spend || 0)}
        />
        <StatCard
          label="Total recebido"
          value={fmtBRL(summary?.revenue || 0)}
          trend="up"
        />
        <StatCard
          label="Retorno (ROAS)"
          value={`${(summary?.roas || 0).toFixed(2)}x`}
          trend={summary?.roas && summary.roas >= 1 ? "up" : "down"}
        />
        <StatCard
          label="Custo por cliente"
          value={fmtBRL(summary?.cpa || 0)}
        />
        <StatCard
          label="Clientes conquistados"
          value={(summary?.conversions || 0).toLocaleString("pt-BR")}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="mb-4">
            <h3 className="font-semibold">Gasto por dia (R$)</h3>
            <p className="text-xs text-gray-500 mt-0.5">Quanto foi investido em cada dia do período</p>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={timeline || []}>
              <defs>
                <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1d6fee" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#1d6fee" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8 }}
                formatter={(v: number) => [`R$ ${v.toLocaleString("pt-BR")}`, "Gasto"]}
              />
              <Area type="monotone" dataKey="spend" stroke="#1d6fee" fill="url(#g1)" name="Gasto" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="mb-4">
            <h3 className="font-semibold">Clientes e retorno por dia</h3>
            <p className="text-xs text-gray-500 mt-0.5">Conversões (barras verdes) e ROAS (barras amarelas) por dia</p>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={timeline || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <YAxis yAxisId="left" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8 }} />
              <Legend wrapperStyle={{ color: "#9ca3af", fontSize: 12 }} />
              <Bar yAxisId="left" dataKey="conversions" fill="#22c55e" name="Clientes" radius={[4, 4, 0, 0]} />
              <Bar yAxisId="right" dataKey="roas" fill="#f59e0b" name="ROAS" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
