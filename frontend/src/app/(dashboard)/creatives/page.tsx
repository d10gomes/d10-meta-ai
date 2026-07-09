"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { CreativeRanking, MetaAccount } from "@/types";

export default function CreativesPage() {
  const { data: accounts } = useQuery<MetaAccount[]>({
    queryKey: ["meta-accounts"],
    queryFn: () => api.get("/meta-accounts").then((r) => r.data),
  });

  const [selectedAccount, setSelectedAccount] = useState<string>("");

  const { data: creatives, isLoading } = useQuery<CreativeRanking[]>({
    queryKey: ["creatives", selectedAccount],
    queryFn: () => api.get(`/creatives/${selectedAccount}`).then((r) => r.data),
    enabled: !!selectedAccount,
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Ranking de Criativos</h2>
        <p className="text-gray-400 text-sm mt-1">Classificação por CTR, CPA e ROAS</p>
      </div>

      <div>
        <label className="text-xs text-gray-400 uppercase mb-1 block">Selecionar Conta</label>
        <select
          value={selectedAccount}
          onChange={(e) => setSelectedAccount(e.target.value)}
          className="bg-surface-card border border-surface-border rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
        >
          <option value="">Selecione...</option>
          {accounts?.map((a) => (
            <option key={a.id} value={a.id}>{a.name || a.ad_account_id}</option>
          ))}
        </select>
      </div>

      {selectedAccount && (
        <div className="card overflow-x-auto">
          {isLoading ? (
            <p className="text-gray-500 py-4">Calculando score...</p>
          ) : creatives?.length === 0 ? (
            <p className="text-gray-500 py-4">Nenhum criativo com dados suficientes</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-surface-border text-left">
                  <th className="pb-3 pr-4">#</th>
                  <th className="pb-3 pr-4">Nome</th>
                  <th className="pb-3 pr-4">Tier</th>
                  <th className="pb-3 pr-4">Score</th>
                  <th className="pb-3 pr-4">CTR</th>
                  <th className="pb-3 pr-4">CPA (R$)</th>
                  <th className="pb-3 pr-4">ROAS</th>
                  <th className="pb-3">Gasto (R$)</th>
                </tr>
              </thead>
              <tbody>
                {creatives?.map((c, i) => (
                  <tr key={c.meta_ad_id} className="border-b border-surface-border last:border-0">
                    <td className="py-3 pr-4 text-gray-500 font-mono">{i + 1}</td>
                    <td className="py-3 pr-4 text-white font-medium max-w-[200px] truncate">{c.name}</td>
                    <td className="py-3 pr-4"><span className={`badge-${c.tier}`}>{c.tier}</span></td>
                    <td className="py-3 pr-4 text-brand-500 font-bold">{c.score}</td>
                    <td className="py-3 pr-4 text-gray-300">{c.avg_ctr.toFixed(2)}%</td>
                    <td className="py-3 pr-4 text-gray-300">{c.avg_cpa.toFixed(2)}</td>
                    <td className="py-3 pr-4 text-gray-300">{c.avg_roas.toFixed(2)}x</td>
                    <td className="py-3 text-gray-300">{c.total_spend.toLocaleString("pt-BR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
