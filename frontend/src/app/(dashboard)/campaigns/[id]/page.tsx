"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, TrendingUp, TrendingDown, DollarSign, Users,
  BarChart2, CheckCircle2, XCircle, Clock, Edit2, Save, X,
  ChevronDown, ChevronUp, Activity,
} from "lucide-react";
import { clsx } from "clsx";
import { toast } from "sonner";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { useApi } from "@/hooks/useApi";

// ─── Types ───────────────────────────────────────────────────────────────────

interface AdSetRow {
  id: string;
  name: string;
  status: string;
  daily_budget: number | null;
  spend: number;
  conversions: number;
  impressions: number;
  clicks: number;
  roas: number;
  cpa: number;
  ctr: number;
  frequency: number;
}

interface ActionRow {
  id: string;
  action_type: string;
  status: string;
  payload: Record<string, unknown> | null;
  created_at: string;
  executed_at: string | null;
  error: string | null;
}

interface TimelinePoint {
  day: string;
  spend: number;
  conversions: number;
  impressions: number;
  clicks: number;
  roas: number;
}

interface CampaignDetail {
  id: string;
  meta_campaign_id: string;
  name: string;
  status: string;
  objective: string;
  daily_budget: number | null;
  account_name: string;
  created_at: string | null;
  period_days: number;
  total_spend: number;
  total_conversions: number;
  timeline: TimelinePoint[];
  adsets: AdSetRow[];
  actions: ActionRow[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmtBRL = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n);

const fmtNum = (n: number) => new Intl.NumberFormat("pt-BR").format(n);

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });

const STATUS_COLORS: Record<string, string> = {
  ACTIVE:  "bg-emerald-500/20 text-emerald-400",
  PAUSED:  "bg-gray-500/20 text-gray-400",
  DELETED: "bg-red-500/20 text-red-400",
};

const ACTION_STATUS_COLORS: Record<string, string> = {
  executed: "text-emerald-400",
  approved: "text-emerald-400",
  failed:   "text-red-400",
  rejected: "text-red-400",
  pending:  "text-yellow-400",
  skipped:  "text-gray-500",
};

const PERIODS = [
  { label: "7 dias",  days: 7  },
  { label: "14 dias", days: 14 },
  { label: "30 dias", days: 30 },
] as const;

// ─── KPI Card ────────────────────────────────────────────────────────────────

function KPI({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-white">{value}</p>
      {sub && <p className="text-[11px] text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

// ─── AdSet Row ───────────────────────────────────────────────────────────────

function AdSetRow({ row }: { row: AdSetRow }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-surface-border last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 py-3 px-4 hover:bg-surface-border/20 transition-colors text-left"
      >
        <span
          className={clsx(
            "w-2 h-2 rounded-full shrink-0",
            row.status === "ACTIVE" ? "bg-emerald-400" : "bg-gray-600"
          )}
        />
        <span className="text-sm text-white flex-1 truncate">{row.name}</span>
        <span className="text-xs font-mono text-gray-400 w-20 text-right">{fmtBRL(row.spend)}</span>
        <span className="text-xs font-mono text-gray-400 w-16 text-right">{row.conversions} conv</span>
        <span
          className={clsx(
            "text-xs font-mono w-14 text-right",
            row.roas >= 3 ? "text-emerald-400" : row.roas >= 1 ? "text-yellow-400" : "text-red-400"
          )}
        >
          {row.roas > 0 ? `${row.roas.toFixed(2)}x` : "—"}
        </span>
        {open ? <ChevronUp size={14} className="text-gray-600 shrink-0" /> : <ChevronDown size={14} className="text-gray-600 shrink-0" />}
      </button>

      {open && (
        <div className="px-4 pb-4 grid grid-cols-3 md:grid-cols-6 gap-3">
          <div className="text-center">
            <p className="text-[10px] text-gray-500">Impressões</p>
            <p className="text-sm font-semibold text-white">{fmtNum(row.impressions)}</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] text-gray-500">Cliques</p>
            <p className="text-sm font-semibold text-white">{fmtNum(row.clicks)}</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] text-gray-500">CTR</p>
            <p className="text-sm font-semibold text-white">{row.ctr.toFixed(2)}%</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] text-gray-500">CPA</p>
            <p className="text-sm font-semibold text-white">{row.cpa > 0 ? fmtBRL(row.cpa) : "—"}</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] text-gray-500">Frequência</p>
            <p className="text-sm font-semibold text-white">{row.frequency > 0 ? `${row.frequency.toFixed(1)}x` : "—"}</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] text-gray-500">Orçamento/dia</p>
            <p className="text-sm font-semibold text-white">{row.daily_budget ? fmtBRL(row.daily_budget) : "—"}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const api = useApi();
  const qc = useQueryClient();

  const [days, setDays] = useState(30);
  const [chartMetric, setChartMetric] = useState<"spend" | "roas" | "conversions">("spend");
  const [editingBudget, setEditingBudget] = useState(false);
  const [budgetInput, setBudgetInput] = useState("");

  const { data, isLoading } = useQuery<CampaignDetail>({
    queryKey: ["campaign-detail", id, days],
    queryFn: () => api.get(`/campaigns/${id}/detail?days=${days}`).then((r) => r.data),
    enabled: !!id,
  });

  const budgetMut = useMutation({
    mutationFn: (brl: number) =>
      api.put(`/campaigns/${id}/budget`, { daily_budget_brl: brl }),
    onSuccess: (res) => {
      toast.success(`Orçamento atualizado para ${fmtBRL(res.data.daily_budget)}/dia`);
      setEditingBudget(false);
      qc.invalidateQueries({ queryKey: ["campaign-detail", id] });
      qc.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: () => toast.error("Erro ao atualizar orçamento"),
  });

  function submitBudget() {
    const val = parseFloat(budgetInput.replace(",", "."));
    if (isNaN(val) || val < 6) {
      toast.error("Mínimo R$ 6,00/dia");
      return;
    }
    budgetMut.mutate(val);
  }

  const CHART_METRICS = [
    { key: "spend" as const,       label: "Gasto (R$)",  color: "#1d6fee" },
    { key: "roas" as const,        label: "ROAS",        color: "#10b981" },
    { key: "conversions" as const, label: "Conversões",  color: "#f59e0b" },
  ];
  const activeMetric = CHART_METRICS.find((m) => m.key === chartMetric)!;

  if (isLoading) {
    return (
      <div className="p-6 space-y-4 max-w-4xl animate-pulse">
        <div className="h-8 bg-gray-800 rounded w-64" />
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 bg-gray-800 rounded-xl" />
          ))}
        </div>
        <div className="h-64 bg-gray-800 rounded-xl" />
      </div>
    );
  }

  if (!data) return null;

  const avgRoas = data.timeline.length > 0
    ? data.timeline.reduce((s, d) => s + d.roas, 0) / data.timeline.filter((d) => d.roas > 0).length
    : 0;

  const chartData = data.timeline.map((d) => ({
    ...d,
    day: fmtDate(d.day),
  }));

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start gap-3">
        <button
          onClick={() => router.push("/campaigns")}
          className="mt-1 p-1.5 hover:bg-surface-card rounded-lg text-gray-500 hover:text-white transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-bold text-white truncate">{data.name}</h1>
            <span className={clsx("text-[11px] px-2 py-0.5 rounded-full font-medium", STATUS_COLORS[data.status] ?? "bg-gray-700 text-gray-400")}>
              {data.status === "ACTIVE" ? "Ativa" : data.status === "PAUSED" ? "Pausada" : data.status}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{data.account_name} · {data.objective}</p>
        </div>

        {/* Period selector */}
        <div className="flex gap-1 bg-surface-card border border-surface-border rounded-xl p-1 shrink-0">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              onClick={() => setDays(p.days)}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                days === p.days ? "bg-brand-500 text-white" : "text-gray-400 hover:text-white"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI
          label="Gasto total"
          value={fmtBRL(data.total_spend)}
          sub={`Últimos ${data.period_days} dias`}
        />
        <KPI
          label="Conversões"
          value={fmtNum(data.total_conversions)}
          sub={data.total_conversions > 0 ? `${fmtBRL(data.total_spend / data.total_conversions)} por conversão` : undefined}
        />
        <KPI
          label="ROAS médio"
          value={avgRoas > 0 ? `${avgRoas.toFixed(2)}x` : "—"}
          sub={avgRoas >= 2 ? "Retorno positivo" : avgRoas > 0 ? "Abaixo do ideal" : "Sem dados"}
        />
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <p className="text-xs text-gray-500 mb-1">Orçamento/dia</p>
          {editingBudget ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">R$</span>
              <input
                type="number"
                value={budgetInput}
                onChange={(e) => setBudgetInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitBudget()}
                className="w-20 bg-surface-border text-white text-sm rounded px-2 py-1 outline-none focus:ring-1 focus:ring-brand-500"
                autoFocus
              />
              <button onClick={submitBudget} disabled={budgetMut.isPending} className="text-emerald-400 hover:text-emerald-300">
                <Save size={14} />
              </button>
              <button onClick={() => setEditingBudget(false)} className="text-gray-500 hover:text-gray-300">
                <X size={14} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <p className="text-xl font-bold text-white">
                {data.daily_budget ? fmtBRL(data.daily_budget) : "—"}
              </p>
              <button
                onClick={() => {
                  setBudgetInput(String(data.daily_budget ?? ""));
                  setEditingBudget(true);
                }}
                className="text-gray-600 hover:text-gray-300 transition-colors"
              >
                <Edit2 size={13} />
              </button>
            </div>
          )}
          <p className="text-[11px] text-gray-500 mt-0.5">Clique no lápis para editar</p>
        </div>
      </div>

      {/* Chart */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-5">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
          <div>
            <h3 className="text-sm font-semibold text-white">{activeMetric.label} por dia</h3>
            <p className="text-xs text-gray-500 mt-0.5">Últimos {data.period_days} dias</p>
          </div>
          <div className="flex gap-1 bg-surface border border-surface-border rounded-lg p-1">
            {CHART_METRICS.map((m) => (
              <button
                key={m.key}
                onClick={() => setChartMetric(m.key)}
                className={clsx(
                  "px-2.5 py-1 rounded text-xs font-medium transition-all",
                  chartMetric === m.key ? "text-white" : "text-gray-500 hover:text-gray-300"
                )}
                style={chartMetric === m.key ? { backgroundColor: m.color + "33", color: m.color } : {}}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {chartData.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-gray-600 text-sm">
            Sem dados para o período selecionado
          </div>
        ) : days <= 14 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} barSize={20}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
              <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} width={45} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#9ca3af" }}
              />
              <Bar dataKey={chartMetric} fill={activeMetric.color} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="gradCamp" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={activeMetric.color} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={activeMetric.color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
              <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} width={45} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#9ca3af" }}
              />
              <Area
                type="monotone"
                dataKey={chartMetric}
                stroke={activeMetric.color}
                strokeWidth={2}
                fill="url(#gradCamp)"
                dot={false}
                activeDot={{ r: 4, fill: activeMetric.color }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* AdSets */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
          <BarChart2 size={14} />
          Conjuntos de Anúncios ({data.adsets.length})
        </h2>

        {data.adsets.length === 0 ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-center text-gray-500 text-sm">
            Nenhum dado disponível para o período
          </div>
        ) : (
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            <div className="flex items-center gap-3 py-2 px-4 border-b border-surface-border">
              <span className="w-2 shrink-0" />
              <span className="text-[10px] text-gray-500 flex-1">Nome</span>
              <span className="text-[10px] text-gray-500 w-20 text-right">Gasto</span>
              <span className="text-[10px] text-gray-500 w-16 text-right">Conv.</span>
              <span className="text-[10px] text-gray-500 w-14 text-right">ROAS</span>
              <span className="w-4 shrink-0" />
            </div>
            {data.adsets.map((a) => (
              <AdSetRow key={a.id} row={a} />
            ))}
          </div>
        )}
      </div>

      {/* Action history */}
      {data.actions.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <Activity size={14} />
            Histórico de Ações dos Agentes
          </h2>
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            {data.actions.map((a) => (
              <div key={a.id} className="flex items-start gap-3 py-3 px-4 border-b border-surface-border last:border-0">
                <div className="mt-0.5">
                  {a.status === "executed" || a.status === "approved" ? (
                    <CheckCircle2 size={14} className="text-emerald-400" />
                  ) : a.status === "failed" || a.status === "rejected" ? (
                    <XCircle size={14} className="text-red-400" />
                  ) : (
                    <Clock size={14} className="text-yellow-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-white font-medium">{a.action_type}</p>
                  {a.payload && (
                    <p className="text-[11px] text-gray-500 mt-0.5 truncate">
                      {JSON.stringify(a.payload)}
                    </p>
                  )}
                  {a.error && <p className="text-[11px] text-red-400 mt-0.5">{a.error}</p>}
                </div>
                <div className="text-right shrink-0">
                  <span className={clsx("text-[11px] font-medium", ACTION_STATUS_COLORS[a.status] ?? "text-gray-500")}>
                    {a.status}
                  </span>
                  <p className="text-[10px] text-gray-600 mt-0.5">
                    {new Date(a.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
