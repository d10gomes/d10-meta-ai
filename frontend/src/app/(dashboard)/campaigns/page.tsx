"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Campaign } from "@/types";

export default function CampaignsPage() {
  const { data: campaigns, isLoading } = useQuery<Campaign[]>({
    queryKey: ["campaigns"],
    queryFn: () => api.get("/campaigns").then((r) => r.data),
  });

  const statusColor: Record<string, string> = {
    ACTIVE: "badge-winner",
    PAUSED: "badge-medium",
    DELETED: "badge-loser",
    ARCHIVED: "badge-low",
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Campanhas</h2>
        <p className="text-gray-400 text-sm mt-1">{campaigns?.length ?? 0} campanhas encontradas</p>
      </div>
      <div className="card overflow-x-auto">
        {isLoading ? (
          <p className="text-gray-500 py-4">Carregando...</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-surface-border text-left">
                <th className="pb-3 pr-4">Nome</th>
                <th className="pb-3 pr-4">Objetivo</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3">Orçamento Diário</th>
              </tr>
            </thead>
            <tbody>
              {campaigns?.map((c) => (
                <tr key={c.id} className="border-b border-surface-border last:border-0 hover:bg-surface-border/30 transition-colors">
                  <td className="py-3 pr-4 text-white font-medium">{c.name || "—"}</td>
                  <td className="py-3 pr-4 text-gray-400 text-xs">{c.objective || "—"}</td>
                  <td className="py-3 pr-4">
                    <span className={statusColor[c.status || ""] || "badge-medium"}>
                      {c.status || "—"}
                    </span>
                  </td>
                  <td className="py-3 text-gray-300">
                    {c.daily_budget ? `R$ ${c.daily_budget.toLocaleString("pt-BR")}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
