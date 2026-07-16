"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import { AlertTriangle, TrendingUp, TrendingDown, Minus, Info } from "lucide-react";
import { clsx } from "clsx";
import { useApi } from "@/hooks/useApi";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PeriodMetrics {
  label: string;
  spend: number;
  clicks: number;
  impressions: number;
  conversions: number;
  cpc: number;
  ctr: number;
  cpa: number;
  cpm: number;
  conv_rate: number;
}

interface WeekPoint {
  week: string;
  spend: number;
  clicks: number;
  conversions: number;
  cpc: number;
  ctr: number;
  cpa: number;
  conv_rate: number;
}

interface BrandResult {
  brand: string;
  period1: PeriodMetrics;
  period2: PeriodMetrics;
  changes: { cpc: number | null; conv_rate: number | null; cpa: number | null; clicks: number | null };
  verdict: "pixel" | "custo" | "ambos" | "ok" | "atencao" | "sem_dados";
  verdict_label: string;
  verdict_color: string;
  timeline: WeekPoint[];
}

interface ComparisonData {
  period_days: number;
  half_days: number;
  generated_at: string;
  brands: BrandResult[];
}

// ─── Constants ───────────────────────────────────────────────────────────────

const VERDICT_STYLES: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  pixel:    { bg: "bg-red-500/8",    border: "border-red-500/30",    text: "text-red-400",    icon: "🔴" },
  custo:    { bg: "bg-orange-500/8", border: "border-orange-500/30", text: "text-orange-400", icon: "🟠" },
  ambos:    { bg: "bg-red-500/8",    border: "border-red-500/30",    text: "text-red-400",    icon: "🚨" },
  ok:       { bg: "bg-emerald-500/8",border: "border-emerald-500/20",text: "text-emerald-400",icon: "✅" },
  atencao:  { bg: "bg-yellow-500/8", border: "border-yellow-500/20", text: "text-yellow-400", icon: "⚠️" },
  sem_dados:{ bg: "bg-gray-500/8",   border: "border-gray-700",      text: "text-gray-500",   icon: "⚪" },
};

const BRAND_COLORS: Record<string, string> = {
  "Circo do Tiru": "#f59e0b",
  "MMABET":        "#3b82f6",
  "DonaldBet":     "#10b981",
};

const PERIODS = [
  { label: "30 dias", days: 30 },
  { label: "60 dias", days: 60 },
  { label: "90 dias", days: 90 },
] as const;

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmtBRL = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 }).format(n);

const fmtPct = (n: number | null, invertColors = false) => {
  if (n === null || n === undefined) return <span className="text-gray-600">—</span>;
  const positive = invertColors ? n < 0 : n > 0;
  const color = Math.abs(n) < 5
    ? "text-gray-400"
    : positive ? "text-emerald-400" : "text-red-400";
  const arrow = n > 2 ? <TrendingUp size={11} className="inline" /> : n < -2 ? <TrendingDown size={11} className="inline" /> : <Minus size={11} className="inline" />;
  return (
    <span className={clsx("flex items-center gap-1 justify-end", color)}>
      {arrow} {n > 0 ? "+" : ""}{n.toFixed(1)}%
    </span>
  );
};

function fmtWeek(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

// ─── Metric compare row ───────────────────────────────────────────────────────

function MetricRow({
  label,
  v1,
  v2,
  change,
  fmt,
  invertChange = false,
  tooltip,
}: {
  label: string;
  v1: number;
  v2: number;
  change: number | null;
  fmt: (n: number) => string;
  invertChange?: boolean;
  tooltip?: string;
}) {
  return (
    <tr className="border-t border-surface-border">
      <td className="py-2.5 pr-4 text-xs text-gray-400 whitespace-nowrap">
        <span className="flex items-center gap-1">
          {label}
          {tooltip && (
            <span title={tooltip} className="text-gray-600 cursor-help">
              <Info size={11} />
            </span>
          )}
        </span>
      </td>
      <td className="py-2.5 pr-4 text-xs text-gray-300 font-mono text-right">{fmt(v1)}</td>
      <td className="py-2.5 pr-4 text-xs font-mono text-right">
        <span className={clsx(
          change !== null && Math.abs(change) > 15
            ? (invertChange ? (change < 0 ? "text-emerald-400" : "text-red-400") : (change > 0 ? "text-emerald-400" : "text-red-400"))
            : "text-gray-300"
        )}>
          {fmt(v2)}
        </span>
      </td>
      <td className="py-2.5 text-xs font-mono text-right">{fmtPct(change, invertChange)}</td>
    </tr>
  );
}

// ─── Brand Card ───────────────────────────────────────────────────────────────

const CHART_METRICS = [
  { key: "cpc" as const,       label: "CPC",             fmt: (v: number) => `R$${v.toFixed(2)}` },
  { key: "conv_rate" as const, label: "Taxa de Conv. %", fmt: (v: number) => `${v.toFixed(2)}%` },
  { key: "cpa" as const,       label: "CPA",             fmt: (v: number) => `R$${v.toFixed(2)}` },
  { key: "clicks" as const,    label: "Cliques",         fmt: (v: number) => v.toFixed(0) },
];

function BrandCard({ brand, halfDays }: { brand: BrandResult; halfDays: number }) {
  const [activeMetric, setActiveMetric] = useState<keyof WeekPoint>("cpc");
  const style = VERDICT_STYLES[brand.verdict] ?? VERDICT_STYLES.sem_dados;
  const color = BRAND_COLORS[brand.brand] ?? "#6b7280";

  const p1 = brand.period1;
  const p2 = brand.period2;
  const ch = brand.changes;

  return (
    <div className={clsx("rounded-2xl border p-5 space-y-5", style.bg, style.border)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <span
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: color }}
            />
            {brand.brand}
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">Comparação: últimos {halfDays * 2} dias</p>
        </div>
        <div className={clsx("flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-medium shrink-0", style.bg, style.border, style.text)}>
          <span>{style.icon}</span>
          <span className="hidden sm:inline">{brand.verdict_label}</span>
          <span className="sm:hidden">{brand.verdict.toUpperCase()}</span>
        </div>
      </div>

      {/* Diagnóstico explicado */}
      {brand.verdict !== "ok" && brand.verdict !== "sem_dados" && (
        <div className={clsx("rounded-xl border px-4 py-3 text-xs leading-relaxed", style.bg, style.border, style.text)}>
          {brand.verdict === "pixel" && (
            <>
              <strong>Sinal de pixel com problema:</strong> os cliques continuam chegando (ou estáveis), mas a taxa de conversão caiu. Isso indica que o pixel não está registrando as compras corretamente — o usuário chega na página mas o evento não dispara.
              <br /><strong>Ação:</strong> Verificar o Meta Pixel Helper, testar o evento de Purchase manualmente, confirmar se o pixel está no obrigadão/confirmação.
            </>
          )}
          {brand.verdict === "custo" && (
            <>
              <strong>Custo de mídia inflado:</strong> o CPC subiu, mas a taxa de conversão se manteve — quando o usuário chega, ele converte normalmente. O problema está na entrega mais cara.
              <br /><strong>Ação:</strong> Revisar público (saturação), testar novos criativos, considerar ampliar faixa de idade ou interesses.
            </>
          )}
          {brand.verdict === "ambos" && (
            <>
              <strong>Dois problemas simultâneos:</strong> o CPC subiu E a taxa de conversão caiu. Pode ser saturação de público somada a problema de pixel, ou criativo fraco gerando tráfego de baixa qualidade sem conversão.
              <br /><strong>Ação:</strong> Checar pixel primeiro (mais fácil de corrigir), depois revisar criativos e público.
            </>
          )}
          {brand.verdict === "atencao" && (
            <>
              <strong>Variação detectada:</strong> há oscilação nas métricas mas ainda dentro de uma faixa de alerta. Monitorar nos próximos dias.
            </>
          )}
        </div>
      )}

      {/* Tabela comparativa */}
      <div className="overflow-x-auto">
        <table className="w-full text-left min-w-[360px]">
          <thead>
            <tr>
              <th className="pb-2 text-[10px] text-gray-500 font-medium uppercase tracking-wider pr-4">Métrica</th>
              <th className="pb-2 text-[10px] text-gray-500 font-medium uppercase tracking-wider pr-4 text-right">
                Período 1<br /><span className="font-normal normal-case">(+ antigo)</span>
              </th>
              <th className="pb-2 text-[10px] text-gray-500 font-medium uppercase tracking-wider pr-4 text-right">
                Período 2<br /><span className="font-normal normal-case">(recente)</span>
              </th>
              <th className="pb-2 text-[10px] text-gray-500 font-medium uppercase tracking-wider text-right">Variação</th>
            </tr>
          </thead>
          <tbody>
            <MetricRow
              label="CPC — Custo por Clique"
              v1={p1.cpc}  v2={p2.cpc}  change={ch.cpc}
              fmt={fmtBRL} invertChange
              tooltip="Se subiu muito e a taxa de conversão ficou estável → custo de mídia inflado"
            />
            <MetricRow
              label="Taxa de Conversão"
              v1={p1.conv_rate} v2={p2.conv_rate} change={ch.conv_rate}
              fmt={(n) => `${n.toFixed(2)}%`}
              tooltip="Se caiu muito e o CPC ficou estável → pixel não está registrando"
            />
            <MetricRow
              label="Cliques"
              v1={p1.clicks} v2={p2.clicks} change={ch.clicks}
              fmt={(n) => n.toLocaleString("pt-BR")}
            />
            <MetricRow
              label="Conversões (compras)"
              v1={p1.conversions} v2={p2.conversions}
              change={p1.conversions > 0 ? (p2.conversions - p1.conversions) / p1.conversions * 100 : null}
              fmt={(n) => n.toLocaleString("pt-BR")}
            />
            <MetricRow
              label="CPA — Custo por Aquisição"
              v1={p1.cpa} v2={p2.cpa} change={ch.cpa}
              fmt={fmtBRL} invertChange
            />
            <MetricRow
              label="CTR — Taxa de Clique"
              v1={p1.ctr} v2={p2.ctr}
              change={p1.ctr > 0 ? (p2.ctr - p1.ctr) / p1.ctr * 100 : null}
              fmt={(n) => `${n.toFixed(2)}%`}
            />
            <MetricRow
              label="CPM — Custo por 1k Impressões"
              v1={p1.cpm} v2={p2.cpm}
              change={p1.cpm > 0 ? (p2.cpm - p1.cpm) / p1.cpm * 100 : null}
              fmt={fmtBRL} invertChange
            />
            <MetricRow
              label="Gasto total"
              v1={p1.spend} v2={p2.spend}
              change={p1.spend > 0 ? (p2.spend - p1.spend) / p1.spend * 100 : null}
              fmt={fmtBRL}
            />
          </tbody>
        </table>
      </div>

      {/* Gráfico de tendência semanal */}
      {brand.timeline.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <span className="text-xs text-gray-500 mr-1">Ver:</span>
            {CHART_METRICS.map((m) => (
              <button
                key={m.key}
                onClick={() => setActiveMetric(m.key as keyof WeekPoint)}
                className={clsx(
                  "px-2.5 py-1 rounded-lg text-xs font-medium transition-all border",
                  activeMetric === m.key
                    ? "text-white border-transparent"
                    : "text-gray-500 border-surface-border hover:text-gray-300"
                )}
                style={activeMetric === m.key ? { backgroundColor: color + "33", borderColor: color + "66", color } : {}}
              >
                {m.label}
              </button>
            ))}
          </div>

          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={brand.timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
              <XAxis
                dataKey="week"
                tickFormatter={fmtWeek}
                tick={{ fill: "#6b7280", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#6b7280", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={40}
                tickFormatter={(v) => {
                  const m = CHART_METRICS.find((x) => x.key === activeMetric);
                  return m ? m.fmt(v).replace("R$", "").trim() : String(v);
                }}
              />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8, fontSize: 12 }}
                labelFormatter={fmtWeek}
                formatter={(v: number) => {
                  const m = CHART_METRICS.find((x) => x.key === activeMetric);
                  return [m ? m.fmt(v) : v, m?.label ?? activeMetric];
                }}
              />
              <Line
                type="monotone"
                dataKey={activeMetric}
                stroke={color}
                strokeWidth={2}
                dot={{ r: 3, fill: color, strokeWidth: 0 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {brand.timeline.length === 0 && (
        <p className="text-sm text-gray-600 text-center py-4">
          Sem dados de campanha para este período.
          <br /><span className="text-xs">Verifique se as campanhas desta marca estão ativas e com dados no banco.</span>
        </p>
      )}
    </div>
  );
}

// ─── Explicação da metodologia ────────────────────────────────────────────────

function Methodology({ days, halfDays }: { days: number; halfDays: number }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-xs text-gray-400 space-y-1.5">
      <p className="text-white font-semibold text-sm flex items-center gap-2">
        <Info size={14} className="text-brand-400" />
        Como funciona o diagnóstico
      </p>
      <p>O período de <strong>{days} dias</strong> é dividido em duas metades de <strong>{halfDays} dias</strong> cada.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
        <div className="bg-red-500/5 border border-red-500/15 rounded-lg p-3">
          <p className="text-red-400 font-medium mb-1">🔴 Problema de pixel</p>
          <p>CPC estável (ou caindo) <strong>+</strong> taxa de conversão caindo.<br />Cliques chegam mas compras não registram.</p>
        </div>
        <div className="bg-orange-500/5 border border-orange-500/15 rounded-lg p-3">
          <p className="text-orange-400 font-medium mb-1">🟠 Custo de mídia inflado</p>
          <p>CPC subindo <strong>+</strong> taxa de conversão estável.<br />Entrega mais cara, pixel funciona ok.</p>
        </div>
        <div className="bg-red-500/5 border border-red-500/15 rounded-lg p-3">
          <p className="text-red-400 font-medium mb-1">🚨 Dois problemas</p>
          <p>CPC subiu <strong>e</strong> taxa de conversão caiu.<br />Checar pixel + rever público e criativos.</p>
        </div>
        <div className="bg-emerald-500/5 border border-emerald-500/15 rounded-lg p-3">
          <p className="text-emerald-400 font-medium mb-1">✅ Tudo ok</p>
          <p>CPC e taxa de conversão estáveis (variação &lt; 15%).<br />Nenhuma ação necessária.</p>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ComparacaoPage() {
  const api = useApi();
  const [days, setDays] = useState(60);

  const { data, isLoading } = useQuery<ComparisonData>({
    queryKey: ["brand-comparison", days],
    queryFn: () => api.get(`/reports/brand-comparison?days=${days}`).then((r) => r.data),
  });

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Comparação por Marca</h1>
          <p className="text-sm text-gray-400 mt-1">
            Diagnóstico: problema de pixel vs custo de mídia — Circo do Tiru · MMABET · DonaldBet
          </p>
        </div>
        <div className="flex gap-1 bg-surface-card border border-surface-border rounded-xl p-1">
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

      {/* Metodologia */}
      {data && <Methodology days={data.period_days} halfDays={data.half_days} />}

      {/* Cards de marca */}
      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="bg-surface-card border border-surface-border rounded-2xl p-5 h-64 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {(data?.brands ?? []).map((brand) => (
            <BrandCard key={brand.brand} brand={brand} halfDays={data!.half_days} />
          ))}
        </div>
      )}

      {data && (
        <p className="text-[11px] text-gray-600 text-center">
          Atualizado em {new Date(data.generated_at).toLocaleString("pt-BR")} · Threshold de variação significativa: 15%
        </p>
      )}
    </div>
  );
}
