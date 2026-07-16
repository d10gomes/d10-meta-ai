"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { translateObjective } from "@/lib/labels";

// ── Períodos ──────────────────────────────────────────────────────────────────

const PERIODS = [
  { label: "Hoje",    days: 1  },
  { label: "Ontem",   days: 2  },
  { label: "7 dias",  days: 7  },
  { label: "14 dias", days: 14 },
  { label: "30 dias", days: 30 },
  { label: "3 meses", days: 90 },
] as const;

const SORT_OPTIONS = [
  { value: "roas",        label: "ROAS" },
  { value: "conversions", label: "Conversões" },
  { value: "ctr",         label: "CTR" },
  { value: "spend",       label: "Gasto" },
  { value: "cpa",         label: "Menor CPA" },
] as const;

// ── Types ─────────────────────────────────────────────────────────────────────

interface Creative {
  id: string;
  meta_ad_id: string;
  name: string;
  status: string;
  campaign_name: string;
  adset_name: string;
  objective: string;
  spend: number;
  impressions: number;
  clicks: number;
  conversions: number;
  revenue: number;
  ctr: number;
  cpa: number;
  roas: number;
  frequency: number;
  cpm: number;
  days_with_data: number;
  score: number;
  grade: "S" | "A" | "B" | "C" | "D";
}

interface CreativesResponse {
  period_days: number;
  total_ads: number;
  total_spend: number;
  total_conversions: number;
  total_revenue: number;
  avg_roas: number;
  winners_count: number;
  losers_count: number;
  items: Creative[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtBRL = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n);

const fmtNum = (n: number) => new Intl.NumberFormat("pt-BR").format(n);

const GRADE_CONFIG: Record<string, { label: string; bg: string; text: string; desc: string }> = {
  S: { label: "S", bg: "bg-purple-500/20", text: "text-purple-300", desc: "Excepcional — escalar agora" },
  A: { label: "A", bg: "bg-green-500/15",  text: "text-green-400",  desc: "Vencedor — manter e escalar" },
  B: { label: "B", bg: "bg-blue-500/15",   text: "text-blue-400",   desc: "Bom — monitorar" },
  C: { label: "C", bg: "bg-yellow-500/15", text: "text-yellow-400", desc: "Regular — testar melhorias" },
  D: { label: "D", bg: "bg-red-500/15",    text: "text-red-400",    desc: "Fraco — considerar pausar" },
};

const STATUS_DOT: Record<string, string> = {
  ACTIVE:   "bg-green-400",
  PAUSED:   "bg-gray-400",
  DELETED:  "bg-red-400",
  ARCHIVED: "bg-gray-600",
};

function GradeBadge({ grade }: { grade: string }) {
  const cfg = GRADE_CONFIG[grade] ?? GRADE_CONFIG.C;
  return (
    <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  );
}

function RoasBadge({ roas }: { roas: number }) {
  const color = roas >= 4 ? "text-purple-300" : roas >= 3 ? "text-green-400" : roas >= 2 ? "text-blue-400" : roas >= 1 ? "text-yellow-400" : "text-red-400";
  return <span className={`text-xs font-bold ${color}`}>{roas > 0 ? `${roas.toFixed(2)}x` : "—"}</span>;
}

// ── Top 3 cards ───────────────────────────────────────────────────────────────

function TopCard({ rank, creative, metric }: { rank: number; creative: Creative; metric: string }) {
  const medals = ["🥇", "🥈", "🥉"];
  const val =
    metric === "roas"        ? `${creative.roas.toFixed(2)}x ROAS` :
    metric === "conversions" ? `${fmtNum(creative.conversions)} conversões` :
    metric === "ctr"         ? `${creative.ctr.toFixed(2)}% CTR` :
    metric === "spend"       ? fmtBRL(creative.spend) :
    creative.cpa > 0         ? `${fmtBRL(creative.cpa)} CPA` : "—";

  return (
    <div className={`card border ${rank === 0 ? "border-yellow-500/30 bg-yellow-500/5" : "border-surface-border"} space-y-3`}>
      <div className="flex items-start gap-3">
        <span className="text-2xl">{medals[rank]}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white truncate" title={creative.name}>{creative.name}</p>
          <p className="text-xs text-gray-500 truncate mt-0.5">{creative.campaign_name}</p>
        </div>
        <GradeBadge grade={creative.grade} />
      </div>
      <div className="text-lg font-bold text-white">{val}</div>
      <div className="grid grid-cols-3 gap-2 text-xs text-gray-400">
        <div>
          <p className="text-gray-600">Gasto</p>
          <p className="text-white font-medium">{fmtBRL(creative.spend)}</p>
        </div>
        <div>
          <p className="text-gray-600">Conversões</p>
          <p className="text-white font-medium">{fmtNum(creative.conversions)}</p>
        </div>
        <div>
          <p className="text-gray-600">CTR</p>
          <p className="text-white font-medium">{creative.ctr.toFixed(2)}%</p>
        </div>
      </div>
    </div>
  );
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function CreativesPage() {
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>(PERIODS[2]);
  const [sort, setSort]     = useState<string>("roas");
  const [search, setSearch] = useState("");
  const [gradeFilter, setGradeFilter] = useState<string>("");
  const [view, setView]     = useState<"table" | "grid">("table");

  const { data, isLoading } = useQuery<CreativesResponse>({
    queryKey: ["creatives", period.days, sort],
    queryFn: () => api.get(`/creatives?days=${period.days}&sort=${sort}&limit=200`).then((r) => r.data),
  });

  const filtered = (data?.items ?? []).filter((c) => {
    const matchSearch = !search || c.name.toLowerCase().includes(search.toLowerCase()) || c.campaign_name.toLowerCase().includes(search.toLowerCase());
    const matchGrade  = !gradeFilter || c.grade === gradeFilter;
    return matchSearch && matchGrade;
  });

  const top3 = (data?.items ?? []).slice(0, 3);

  return (
    <div className="space-y-6">
      {/* Header + período */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold">Criativos</h2>
          <p className="text-gray-400 text-sm mt-1">Desempenho de todos os anúncios ativos e pausados</p>
        </div>
        <div className="flex gap-1 bg-surface-card border border-surface-border rounded-xl p-1">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                period.days === p.days ? "bg-brand-500 text-white shadow" : "text-gray-400 hover:text-white"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPIs de resumo */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {[
            { label: "Anúncios",      value: data.total_ads },
            { label: "Gasto total",   value: fmtBRL(data.total_spend) },
            { label: "Receita",       value: fmtBRL(data.total_revenue) },
            { label: "ROAS médio",    value: `${data.avg_roas.toFixed(2)}x`, color: data.avg_roas >= 2 ? "text-green-400" : "text-red-400" },
            { label: "Conversões",    value: fmtNum(data.total_conversions) },
            { label: "🏆 Vencedores", value: data.winners_count, color: "text-green-400" },
            { label: "⚠️ Fracos",    value: data.losers_count,  color: data.losers_count > 0 ? "text-red-400" : "text-gray-400" },
          ].map(({ label, value, color }) => (
            <div key={label} className="card text-center py-3">
              <p className={`text-xl font-bold ${color ?? "text-white"}`}>{value}</p>
              <p className="text-xs text-gray-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Top 3 vencedores */}
      {top3.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-base font-semibold">Top 3 — melhores resultados</h3>
            <span className="text-xs text-gray-500">ordenado por {SORT_OPTIONS.find((s) => s.value === sort)?.label}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {top3.map((c, i) => (
              <TopCard key={c.id} rank={i} creative={c} metric={sort} />
            ))}
          </div>
        </div>
      )}

      {/* Filtros + ordenação */}
      <div className="flex gap-3 flex-wrap items-center">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar anúncio ou campanha..."
          className="flex-1 min-w-[180px] bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500"
        />

        {/* Grade filter */}
        <div className="flex gap-1">
          {["", "S", "A", "B", "C", "D"].map((g) => {
            const cfg = g ? GRADE_CONFIG[g] : null;
            return (
              <button
                key={g || "all"}
                onClick={() => setGradeFilter(g)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  gradeFilter === g
                    ? "border-brand-500 text-white bg-brand-500/20"
                    : "border-surface-border text-gray-400 hover:text-white"
                } ${cfg ? `${cfg.bg} ${cfg.text}` : ""}`}
              >
                {g || "Todos"}
              </button>
            );
          })}
        </div>

        {/* Ordenação */}
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="bg-surface-card border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>Ordenar por {o.label}</option>
          ))}
        </select>

        <span className="text-xs text-gray-500">{filtered.length} criativos</span>
      </div>

      {/* Tabela de criativos */}
      {isLoading ? (
        <div className="card text-center py-12 text-gray-500 text-sm">Carregando criativos...</div>
      ) : filtered.length === 0 ? (
        <div className="card text-center py-12 text-gray-500 text-sm">
          Nenhum criativo com dados no período selecionado.
          <p className="text-xs mt-1 text-gray-600">O Scanner precisa ter coletado dados para este período.</p>
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="text-gray-500 border-b border-surface-border text-left text-xs uppercase tracking-wider">
                <th className="pb-3 pr-3 w-8">#</th>
                <th className="pb-3 pr-3">Grade</th>
                <th className="pb-3 pr-3">Anúncio / Campanha</th>
                <th className="pb-3 pr-3">Status</th>
                <th className="pb-3 pr-3 text-right">Gasto</th>
                <th className="pb-3 pr-3 text-right">ROAS</th>
                <th className="pb-3 pr-3 text-right">Conversões</th>
                <th className="pb-3 pr-3 text-right">CTR</th>
                <th className="pb-3 pr-3 text-right">CPA</th>
                <th className="pb-3 pr-3 text-right">Freq.</th>
                <th className="pb-3 text-right">Dias</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr
                  key={c.id}
                  className="border-b border-surface-border last:border-0 hover:bg-surface-border/20 transition-colors"
                >
                  <td className="py-3 pr-3 text-gray-600 text-xs">{i + 1}</td>
                  <td className="py-3 pr-3">
                    <div title={GRADE_CONFIG[c.grade]?.desc}>
                      <GradeBadge grade={c.grade} />
                    </div>
                  </td>
                  <td className="py-3 pr-3 max-w-[260px]">
                    <p className="text-white text-sm font-medium truncate" title={c.name}>{c.name}</p>
                    <p className="text-gray-500 text-xs truncate mt-0.5" title={c.campaign_name}>
                      {c.campaign_name}
                    </p>
                  </td>
                  <td className="py-3 pr-3">
                    <span className="flex items-center gap-1.5 text-xs text-gray-400">
                      <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[c.status] ?? "bg-gray-500"}`} />
                      {c.status === "ACTIVE" ? "Ativo" : c.status === "PAUSED" ? "Pausado" : c.status}
                    </span>
                  </td>
                  <td className="py-3 pr-3 text-right text-gray-300 text-xs font-mono">{fmtBRL(c.spend)}</td>
                  <td className="py-3 pr-3 text-right"><RoasBadge roas={c.roas} /></td>
                  <td className="py-3 pr-3 text-right">
                    <span className={`text-xs font-semibold ${c.conversions > 0 ? "text-green-400" : "text-gray-600"}`}>
                      {c.conversions > 0 ? fmtNum(c.conversions) : "—"}
                    </span>
                  </td>
                  <td className="py-3 pr-3 text-right text-xs text-gray-300 font-mono">
                    {c.ctr > 0 ? `${c.ctr.toFixed(2)}%` : "—"}
                  </td>
                  <td className="py-3 pr-3 text-right text-xs text-gray-300 font-mono">
                    {c.cpa > 0 ? fmtBRL(c.cpa) : "—"}
                  </td>
                  <td className="py-3 pr-3 text-right">
                    <span className={`text-xs ${c.frequency > 4 ? "text-red-400 font-semibold" : c.frequency > 2.5 ? "text-yellow-400" : "text-gray-400"}`}>
                      {c.frequency > 0 ? `${c.frequency.toFixed(1)}x` : "—"}
                    </span>
                  </td>
                  <td className="py-3 text-right text-xs text-gray-600">{c.days_with_data}d</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Legenda grades */}
      <div className="card">
        <p className="text-xs font-semibold text-gray-400 mb-3">Legenda de classificação</p>
        <div className="flex flex-wrap gap-4">
          {Object.entries(GRADE_CONFIG).map(([g, cfg]) => (
            <div key={g} className="flex items-center gap-2">
              <GradeBadge grade={g} />
              <span className="text-xs text-gray-400">{cfg.desc}</span>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-3">
          💡 Frequência acima de 4x indica público saturado — hora de renovar o criativo.
        </p>
      </div>
    </div>
  );
}
