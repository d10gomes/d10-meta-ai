"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Diagnosis } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";

const ISSUE_LABELS: Record<string, string> = {
  LOW_CTR: "CTR Baixo",
  HIGH_CPA: "CPA Alto",
  HIGH_FREQUENCY: "Frequência Alta",
  NO_CONVERSIONS: "Sem Conversões",
  CREATIVE_SATURATION: "Saturação de Criativo",
  LOW_ROAS: "ROAS Baixo",
  HIGH_CPM: "CPM Alto",
};

export default function DiagnosesPage() {
  const { data: diagnoses, isLoading } = useQuery<Diagnosis[]>({
    queryKey: ["diagnoses"],
    queryFn: () => api.get("/diagnoses").then((r) => r.data),
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Diagnósticos</h2>
        <p className="text-gray-400 text-sm mt-1">{diagnoses?.length ?? 0} problemas ativos detectados pelo Doctor Agent</p>
      </div>
      <div className="card">
        {isLoading ? (
          <p className="text-gray-500 py-4">Analisando...</p>
        ) : diagnoses?.length === 0 ? (
          <p className="text-green-400 py-4">✓ Nenhum problema detectado</p>
        ) : (
          <div className="space-y-3">
            {diagnoses?.map((d) => (
              <div key={d.id} className="flex items-start justify-between py-3 border-b border-surface-border last:border-0">
                <div className="flex items-start gap-3">
                  <span className={`badge-${d.severity} mt-0.5 whitespace-nowrap`}>{d.severity.toUpperCase()}</span>
                  <div>
                    <p className="text-white text-sm font-medium">{ISSUE_LABELS[d.issue_type] || d.issue_type}</p>
                    <p className="text-gray-500 text-xs mt-0.5">
                      {d.entity_type} • {d.entity_id}
                    </p>
                    {d.details && (
                      <p className="text-gray-400 text-xs mt-1">
                        {Object.entries(d.details).map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(2) : v}`).join(" | ")}
                      </p>
                    )}
                  </div>
                </div>
                <span className="text-gray-500 text-xs whitespace-nowrap ml-4">
                  {formatDistanceToNow(new Date(d.created_at), { addSuffix: true, locale: ptBR })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
