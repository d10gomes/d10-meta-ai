"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { translateIssue } from "@/lib/labels";
import type { Diagnosis } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";

const SEVERITY_ICON: Record<string, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🟢",
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Crítico — requer atenção imediata",
  high: "Alto — agir em breve",
  medium: "Atenção — monitorar",
  low: "Baixo — informativo",
};

const ENTITY_LABEL: Record<string, string> = {
  campaign: "Campanha",
  adset: "Conjunto de anúncios",
  ad: "Anúncio",
};

const ISSUE_TIPS: Record<string, string> = {
  high_cpa: "Tente ajustar o público-alvo ou trocar o criativo. O custo por cliente está acima do esperado.",
  low_roas: "Cada R$ 1 gasto está trazendo menos de R$ 1 de volta. Revise os anúncios e o público.",
  high_frequency: "As mesmas pessoas estão vendo o anúncio muitas vezes. Troque o criativo ou amplie o público.",
  low_ctr: "Poucas pessoas estão clicando. O criativo pode não estar chamando atenção — teste uma imagem nova.",
  budget_underutilized: "O orçamento não está sendo gasto completamente. O lance pode estar muito restritivo.",
  audience_saturation: "O público esgotou. Adicione novos interesses ou crie um público semelhante (lookalike).",
  no_conversions: "Essa campanha não gerou nenhum resultado. Verifique o pixel e a configuração de conversão.",
  high_spend_no_result: "Dinheiro sendo gasto sem retorno. Pause e revise a estratégia.",
  creative_fatigue: "O criativo está cansado. As pessoas pararam de responder — troque por algo novo.",
  bid_too_low: "O lance está muito baixo e o anúncio não está sendo entregue. Aumente o lance.",
  learning_phase: "Normal — a campanha está em fase de aprendizado. Aguarde 7 dias antes de fazer alterações.",
  budget_limited: "O orçamento está limitando o alcance. Considere aumentar para aproveitar melhor o horário.",
};

const DETAIL_LABELS: Record<string, string> = {
  cpa: "Custo por cliente",
  roas: "Retorno sobre investimento",
  frequency: "Frequência média",
  ctr: "Taxa de cliques",
  spend: "Gasto total",
  conversions: "Conversões",
  budget_utilization: "Uso do orçamento",
};

function formatDetailValue(key: string, value: unknown): string {
  if (typeof value !== "number") return String(value);
  if (key === "cpa" || key === "spend") return `R$ ${value.toFixed(2)}`;
  if (key === "roas") return `${value.toFixed(2)}x`;
  if (key === "ctr" || key === "budget_utilization") return `${value.toFixed(1)}%`;
  return value.toFixed(2);
}

export default function DiagnosesPage() {
  const { data: diagnoses, isLoading } = useQuery<Diagnosis[]>({
    queryKey: ["diagnoses"],
    queryFn: () => api.get("/diagnoses").then((r) => r.data),
  });

  const critical = diagnoses?.filter((d) => d.severity === "critical") ?? [];
  const high = diagnoses?.filter((d) => d.severity === "high") ?? [];
  const others = diagnoses?.filter((d) => d.severity !== "critical" && d.severity !== "high") ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Diagnóstico das Campanhas</h2>
        <p className="text-gray-400 text-sm mt-1">
          {diagnoses?.length ?? 0} problema{diagnoses?.length !== 1 ? "s" : ""} detectado{diagnoses?.length !== 1 ? "s" : ""} — análise feita pelo Agente Doutor
        </p>
      </div>

      {isLoading && (
        <div className="card text-center py-12 text-gray-500">Analisando suas campanhas...</div>
      )}

      {!isLoading && diagnoses?.length === 0 && (
        <div className="card border border-green-500/20 bg-green-500/5 text-center py-12">
          <span className="text-4xl">✅</span>
          <p className="text-green-400 font-semibold mt-3 text-lg">Tudo certo!</p>
          <p className="text-gray-500 text-sm mt-1">Nenhum problema detectado nas suas campanhas agora.</p>
        </div>
      )}

      {/* Critical first */}
      {critical.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-red-400">🔴 Crítico — aja agora</p>
          {critical.map((d) => <DiagnosisCard key={d.id} d={d} />)}
        </div>
      )}

      {high.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-orange-400">🟠 Alto — agir em breve</p>
          {high.map((d) => <DiagnosisCard key={d.id} d={d} />)}
        </div>
      )}

      {others.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Outros avisos</p>
          {others.map((d) => <DiagnosisCard key={d.id} d={d} />)}
        </div>
      )}

      {!isLoading && (diagnoses?.length ?? 0) > 0 && (
        <div className="card border border-brand-500/20 bg-brand-500/5 text-center py-5">
          <p className="text-brand-300 font-medium text-sm">
            💡 Quer corrigir esses problemas automaticamente?
          </p>
          <p className="text-gray-500 text-xs mt-1">
            Acesse o <strong className="text-gray-300">Maestro</strong> e diga:{" "}
            <em className="text-gray-400">"Corrija os problemas detectados nas minhas campanhas"</em>
          </p>
        </div>
      )}
    </div>
  );
}

function DiagnosisCard({ d }: { d: Diagnosis }) {
  const icon = SEVERITY_ICON[d.severity] || "🟡";
  const severityLabel = SEVERITY_LABEL[d.severity] || d.severity;
  const tip = ISSUE_TIPS[d.issue_type] || ISSUE_TIPS[d.issue_type?.toLowerCase()] || null;
  const entityLabel = ENTITY_LABEL[d.entity_type] || d.entity_type;

  return (
    <div className="card border border-surface-border">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="text-xl mt-0.5">{icon}</span>
          <div className="flex-1">
            <p className="text-white font-semibold text-sm">{translateIssue(d.issue_type)}</p>
            <p className="text-xs text-gray-500 mt-0.5">{severityLabel}</p>
            <p className="text-xs text-gray-500 mt-1">
              {entityLabel}
              {d.entity_id && <span className="ml-1 font-mono text-gray-600 text-[10px]">({d.entity_id.slice(-8)}…)</span>}
            </p>
          </div>
        </div>
        <span className="text-xs text-gray-600 whitespace-nowrap">
          {formatDistanceToNow(new Date(d.created_at), { addSuffix: true, locale: ptBR })}
        </span>
      </div>

      {/* Metrics in plain language */}
      {d.details && Object.keys(d.details).length > 0 && (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2">
          {Object.entries(d.details).map(([k, v]) => (
            <div key={k} className="bg-surface-border/30 rounded-lg px-3 py-2">
              <p className="text-xs text-gray-500">{DETAIL_LABELS[k] || k.replace(/_/g, " ")}</p>
              <p className="text-sm font-semibold text-white mt-0.5">{formatDetailValue(k, v)}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tip */}
      {tip && (
        <div className="mt-3 bg-amber-500/5 border border-amber-500/20 rounded-lg px-3 py-2">
          <p className="text-xs text-amber-300">
            <strong>O que fazer:</strong> {tip}
          </p>
        </div>
      )}
    </div>
  );
}
