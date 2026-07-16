"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { translateObjective, translateStatus, formatBudget } from "@/lib/labels";
import type { Campaign } from "@/types";

function healthScore(c: Campaign): { icon: string; label: string; color: string } {
  if (c.status === "PAUSED") return { icon: "⚪", label: "Pausada", color: "text-gray-400" };
  if (c.status === "DELETED" || c.status === "ARCHIVED") return { icon: "🔴", label: "Inativa", color: "text-red-400" };
  if (c.status === "ACTIVE") return { icon: "🟢", label: "Boa", color: "text-green-400" };
  return { icon: "🟡", label: "Atenção", color: "text-yellow-400" };
}

const STATUS_STYLE: Record<string, string> = {
  ACTIVE: "bg-green-500/10 text-green-400 border border-green-500/20",
  PAUSED: "bg-gray-500/10 text-gray-400 border border-gray-600/30",
  DELETED: "bg-red-500/10 text-red-400 border border-red-500/20",
  ARCHIVED: "bg-gray-500/10 text-gray-500 border border-gray-700",
};

export default function CampaignsPage() {
  const { data: campaigns, isLoading } = useQuery<Campaign[]>({
    queryKey: ["campaigns"],
    queryFn: () => api.get("/campaigns").then((r) => r.data),
  });

  const active = campaigns?.filter((c) => c.status === "ACTIVE") ?? [];
  const paused = campaigns?.filter((c) => c.status === "PAUSED") ?? [];
  const totalBudget = active.reduce((sum, c) => sum + (c.daily_budget ?? 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Campanhas</h2>
        <p className="text-gray-400 text-sm mt-1">
          {campaigns?.length ?? 0} campanhas encontradas na sua conta do Meta Ads
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card flex items-center gap-4">
          <span className="text-3xl">🟢</span>
          <div>
            <p className="text-2xl font-bold text-white">{active.length}</p>
            <p className="text-sm text-gray-400">Campanhas ativas</p>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <span className="text-3xl">⚪</span>
          <div>
            <p className="text-2xl font-bold text-white">{paused.length}</p>
            <p className="text-sm text-gray-400">Pausadas</p>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <span className="text-3xl">💰</span>
          <div>
            <p className="text-2xl font-bold text-white">{formatBudget(totalBudget)}</p>
            <p className="text-sm text-gray-400">Orçamento diário ativo</p>
          </div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        {isLoading ? (
          <p className="text-gray-500 py-8 text-center">Carregando campanhas...</p>
        ) : campaigns?.length === 0 ? (
          <p className="text-gray-500 py-8 text-center">Nenhuma campanha encontrada.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-surface-border text-left text-xs uppercase tracking-wider">
                <th className="pb-3 pr-4">Saúde</th>
                <th className="pb-3 pr-4">Nome da Campanha</th>
                <th className="pb-3 pr-4">Objetivo</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3">Orçamento Diário</th>
              </tr>
            </thead>
            <tbody>
              {campaigns?.map((c) => {
                const health = healthScore(c);
                return (
                  <tr
                    key={c.id}
                    className="border-b border-surface-border last:border-0 hover:bg-surface-border/20 transition-colors"
                  >
                    <td className="py-3 pr-4">
                      <span title={health.label} className={`text-base ${health.color}`}>
                        {health.icon}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-white font-medium max-w-xs truncate" title={c.name || ""}>
                      {c.name || "—"}
                    </td>
                    <td className="py-3 pr-4 text-gray-400 text-xs">
                      {translateObjective(c.objective)}
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${STATUS_STYLE[c.status || ""] || "text-gray-400"}`}>
                        {translateStatus(c.status)}
                      </span>
                    </td>
                    <td className="py-3 text-gray-300 font-medium">
                      {formatBudget(c.daily_budget)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-gray-600 text-center">
        💡 Dica: acesse o <strong className="text-gray-400">Maestro</strong> para otimizar campanhas com um único comando em português
      </p>
    </div>
  );
}
