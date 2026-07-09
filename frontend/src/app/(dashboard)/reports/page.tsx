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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Relatórios</h2>
        <div className="flex gap-2">
          {[7, 14, 30, 60, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                days === d ? "bg-brand-500 text-white" : "bg-surface-card text-gray-400 hover:text-white border border-surface-border"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard label="Gasto Total" value={`R$ ${(summary?.spend || 0).toLocaleString("pt-BR")}`} />
        <StatCard label="Receita" value={`R$ ${(summary?.revenue || 0).toLocaleString("pt-BR")}`} trend="up" />
        <StatCard label="ROAS" value={`${(summary?.roas || 0).toFixed(2)}x`} trend={summary?.roas && summary.roas >= 1 ? "up" : "down"} />
        <StatCard label="CPA" value={`R$ ${(summary?.cpa || 0).toFixed(2)}`} />
        <StatCard label="Conversões" value={summary?.conversions || 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="font-semibold mb-4">Gasto Diário (R$)</h3>
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
              <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8 }} />
              <Area type="monotone" dataKey="spend" stroke="#1d6fee" fill="url(#g1)" name="Gasto" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="font-semibold mb-4">Conversões e ROAS Diário</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={timeline || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <YAxis yAxisId="left" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8 }} />
              <Legend wrapperStyle={{ color: "#9ca3af", fontSize: 12 }} />
              <Bar yAxisId="left" dataKey="conversions" fill="#22c55e" name="Conversões" radius={[4, 4, 0, 0]} />
              <Bar yAxisId="right" dataKey="roas" fill="#f59e0b" name="ROAS" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
