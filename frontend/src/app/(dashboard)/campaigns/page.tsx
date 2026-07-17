"use client";
import { Suspense, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Plus, Search, Play, Pause, Loader2, Copy, X } from "lucide-react";
import { api } from "@/lib/api";
import { translateObjective, translateStatus, formatBudget } from "@/lib/labels";
import type { Campaign } from "@/types";
import { toast } from "sonner";

type CampaignWithMetrics = Campaign & {
  spend_7d?: number | null;
  conversions_7d?: number | null;
  roas_7d?: number | null;
  cpa_7d?: number | null;
  ctr_7d?: number | null;
  clicks_7d?: number | null;
  impressions_7d?: number | null;
};

function healthScore(c: CampaignWithMetrics): { icon: string; label: string; color: string } {
  if (c.status === "PAUSED") return { icon: "⚪", label: "Pausada", color: "text-gray-400" };
  if (c.status === "DELETED" || c.status === "ARCHIVED") return { icon: "🔴", label: "Inativa", color: "text-red-400" };
  if (c.status === "ACTIVE") return { icon: "🟢", label: "Ativa", color: "text-green-400" };
  return { icon: "🟡", label: "Atenção", color: "text-yellow-400" };
}

const STATUS_STYLE: Record<string, string> = {
  ACTIVE:   "bg-green-500/10 text-green-400 border border-green-500/20",
  PAUSED:   "bg-gray-500/10 text-gray-400 border border-gray-600/30",
  DELETED:  "bg-red-500/10 text-red-400 border border-red-500/20",
  ARCHIVED: "bg-gray-500/10 text-gray-500 border border-gray-700",
};

function fmtBRL(v?: number | null) {
  if (v == null) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v);
}

function RoasBadge({ roas }: { roas?: number | null }) {
  if (roas == null) return <span className="text-gray-600 text-xs">—</span>;
  const color = roas >= 2 ? "text-green-400" : roas >= 1 ? "text-yellow-400" : "text-red-400";
  return <span className={`text-xs font-semibold ${color}`}>{roas.toFixed(2)}x</span>;
}

// ── Inner page (uses useSearchParams — must be inside Suspense) ───────────────

function CampaignsInner() {
  const searchParams = useSearchParams();
  const justCreated = searchParams.get("created") === "1";
  const qc = useQueryClient();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "ACTIVE" | "PAUSED">("ALL");
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [duplicating, setDuplicating] = useState<{ id: string; name: string } | null>(null);
  const [dupName, setDupName] = useState("");

  const { data: campaigns, isLoading } = useQuery<CampaignWithMetrics[]>({
    queryKey: ["campaigns"],
    queryFn: () => api.get("/campaigns").then((r) => r.data),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.put(`/campaigns/${id}/status`, { status }).then((r) => r.data),
    onMutate: ({ id }) => setTogglingId(id),
    onSettled: () => {
      setTogglingId(null);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });

  const dupMutation = useMutation({
    mutationFn: ({ id, new_name }: { id: string; new_name: string }) =>
      api.post(`/campaigns/${id}/duplicate`, { new_name }).then((r) => r.data),
    onSuccess: (res) => {
      toast.success(res.message ?? "Campanha duplicada com sucesso!");
      setDuplicating(null);
      setDupName("");
      qc.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: () => toast.error("Erro ao duplicar campanha"),
  });

  function openDuplicate(c: CampaignWithMetrics) {
    setDuplicating({ id: c.id, name: c.name ?? "" });
    setDupName(`${c.name ?? ""} — Cópia`);
  }

  function submitDuplicate() {
    if (!duplicating || !dupName.trim()) return;
    dupMutation.mutate({ id: duplicating.id, new_name: dupName.trim() });
  }

  // Filter logic
  const filtered = (campaigns ?? []).filter((c) => {
    const matchSearch = !search || (c.name ?? "").toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "ALL" || c.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const active = campaigns?.filter((c) => c.status === "ACTIVE") ?? [];
  const paused = campaigns?.filter((c) => c.status === "PAUSED") ?? [];
  const totalBudget = active.reduce((sum, c) => sum + (c.daily_budget ?? 0), 0);
  const totalSpend7d = (campaigns ?? []).reduce((sum, c) => sum + (c.spend_7d ?? 0), 0);

  return (
    <div className="space-y-6">
      {justCreated && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4 text-sm text-green-300 flex items-center gap-3">
          ✅ <span>Campanha criada com sucesso! Está <strong>pausada</strong> — ative quando quiser.</span>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold">Campanhas</h2>
          <p className="text-gray-400 text-sm mt-1">
            {campaigns?.length ?? 0} campanhas • {active.length} ativas
          </p>
        </div>
        <Link href="/campaigns/new" className="flex items-center gap-2 btn-primary">
          <Plus size={16} /> Nova Campanha
        </Link>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="card flex items-center gap-3">
          <span className="text-2xl">🟢</span>
          <div>
            <p className="text-xl font-bold text-white">{active.length}</p>
            <p className="text-xs text-gray-400">Ativas</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <span className="text-2xl">⚪</span>
          <div>
            <p className="text-xl font-bold text-white">{paused.length}</p>
            <p className="text-xs text-gray-400">Pausadas</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <span className="text-2xl">💰</span>
          <div>
            <p className="text-xl font-bold text-white">{formatBudget(totalBudget)}</p>
            <p className="text-xs text-gray-400">Orçamento/dia</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <span className="text-2xl">📊</span>
          <div>
            <p className="text-xl font-bold text-white">{fmtBRL(totalSpend7d)}</p>
            <p className="text-xs text-gray-400">Gasto (7 dias)</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[180px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar campanha..."
            className="w-full bg-surface border border-surface-border rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500"
          />
        </div>
        <div className="flex gap-2">
          {(["ALL", "ACTIVE", "PAUSED"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === s
                  ? "bg-brand-500 text-white"
                  : "bg-surface-card border border-surface-border text-gray-400 hover:text-white"
              }`}
            >
              {s === "ALL" ? "Todas" : s === "ACTIVE" ? "🟢 Ativas" : "⚪ Pausadas"}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-x-auto">
        {isLoading ? (
          <p className="text-gray-500 py-8 text-center">Carregando campanhas...</p>
        ) : filtered.length === 0 ? (
          <p className="text-gray-500 py-8 text-center">
            {search ? `Nenhuma campanha com "${search}"` : "Nenhuma campanha encontrada."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-surface-border text-left text-xs uppercase tracking-wider">
                <th className="pb-3 pr-3">Saúde</th>
                <th className="pb-3 pr-3">Nome</th>
                <th className="pb-3 pr-3">Status</th>
                <th className="pb-3 pr-3 text-right">Orç./dia</th>
                <th className="pb-3 pr-3 text-right">Gasto 7d</th>
                <th className="pb-3 pr-3 text-right">Conv. 7d</th>
                <th className="pb-3 pr-3 text-right">CPA</th>
                <th className="pb-3 pr-3 text-right">ROAS</th>
                <th className="pb-3 pr-3 text-right">CTR</th>
                <th className="pb-3 pr-3 text-right">Cliques</th>
                <th className="pb-3">Ação</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => {
                const health = healthScore(c);
                const isToggling = togglingId === c.id;
                const canToggle = c.status === "ACTIVE" || c.status === "PAUSED";
                return (
                  <tr
                    key={c.id}
                    className="border-b border-surface-border last:border-0 hover:bg-surface-border/20 transition-colors"
                  >
                    <td className="py-3 pr-3">
                      <span title={health.label}>{health.icon}</span>
                    </td>
                    <td className="py-3 pr-3 max-w-[180px]">
                      <Link
                        href={`/campaigns/${c.id}`}
                        className="text-white font-medium hover:text-brand-400 transition-colors block truncate"
                        title={c.name ?? ""}
                      >
                        {c.name || "—"}
                      </Link>
                    </td>
                    <td className="py-3 pr-3">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLE[c.status ?? ""] || "text-gray-400"}`}>
                        {translateStatus(c.status)}
                      </span>
                    </td>
                    <td className="py-3 pr-3 text-gray-300 text-xs text-right whitespace-nowrap">
                      {formatBudget(c.daily_budget)}
                    </td>
                    <td className="py-3 pr-3 text-gray-300 text-xs text-right whitespace-nowrap">
                      {c.spend_7d != null ? fmtBRL(c.spend_7d) : <span className="text-gray-600">—</span>}
                    </td>
                    <td className="py-3 pr-3 text-right">
                      {c.conversions_7d != null ? (
                        <span className={`text-xs font-semibold ${c.conversions_7d > 0 ? "text-green-400" : "text-gray-500"}`}>
                          {c.conversions_7d.toLocaleString("pt-BR")}
                        </span>
                      ) : <span className="text-gray-600 text-xs">—</span>}
                    </td>
                    <td className="py-3 pr-3 text-right">
                      {c.cpa_7d != null ? (
                        <span className="text-xs font-semibold text-yellow-400">{fmtBRL(c.cpa_7d)}</span>
                      ) : <span className="text-gray-600 text-xs">—</span>}
                    </td>
                    <td className="py-3 pr-3 text-right">
                      <RoasBadge roas={c.roas_7d} />
                    </td>
                    <td className="py-3 pr-3 text-right">
                      {c.ctr_7d != null ? (
                        <span className="text-xs text-gray-300">{c.ctr_7d.toFixed(2)}%</span>
                      ) : <span className="text-gray-600 text-xs">—</span>}
                    </td>
                    <td className="py-3 pr-3 text-right">
                      {c.clicks_7d != null ? (
                        <span className="text-xs text-gray-300">{c.clicks_7d.toLocaleString("pt-BR")}</span>
                      ) : <span className="text-gray-600 text-xs">—</span>}
                    </td>
                    <td className="py-3">
                      <div className="flex items-center gap-1.5">
                        {canToggle && (
                          <button
                            disabled={isToggling || statusMutation.isPending}
                            onClick={() =>
                              statusMutation.mutate({
                                id: c.id,
                                status: c.status === "ACTIVE" ? "PAUSED" : "ACTIVE",
                              })
                            }
                            title={c.status === "ACTIVE" ? "Pausar campanha" : "Ativar campanha"}
                            className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                              c.status === "ACTIVE"
                                ? "border-gray-600 text-gray-400 hover:border-yellow-500/50 hover:text-yellow-400"
                                : "border-gray-600 text-gray-400 hover:border-green-500/50 hover:text-green-400"
                            }`}
                          >
                            {isToggling ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : c.status === "ACTIVE" ? (
                              <><Pause size={12} /> Pausar</>
                            ) : (
                              <><Play size={12} /> Ativar</>
                            )}
                          </button>
                        )}
                        <button
                          onClick={() => openDuplicate(c)}
                          title="Duplicar campanha"
                          className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border border-gray-600 text-gray-400 hover:border-brand-500/50 hover:text-brand-400 transition-colors"
                        >
                          <Copy size={12} /> Duplicar
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-gray-600 text-center">
        💡 Use o <strong className="text-gray-400">Maestro</strong> para otimizar várias campanhas de uma vez com um comando em português
      </p>

      {/* Modal duplicar */}
      {duplicating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface-card border border-surface-border rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <Copy size={16} className="text-brand-400" />
                Duplicar Campanha
              </h3>
              <button
                onClick={() => { setDuplicating(null); setDupName(""); }}
                className="text-gray-500 hover:text-white transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <p className="text-xs text-gray-500 mb-1">Original:</p>
            <p className="text-sm text-gray-300 mb-4 truncate">{duplicating.name}</p>

            <label className="block text-xs text-gray-400 mb-1.5">Nome da cópia</label>
            <input
              type="text"
              value={dupName}
              onChange={(e) => setDupName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitDuplicate()}
              placeholder="Nome da nova campanha..."
              className="w-full bg-surface-border border border-surface-border text-white text-sm rounded-xl px-3 py-2.5 outline-none focus:ring-1 focus:ring-brand-500 placeholder-gray-600"
              autoFocus
            />

            <p className="text-[11px] text-gray-600 mt-2">
              A cópia inclui todos os conjuntos e anúncios. Será criada <strong className="text-gray-400">pausada</strong>.
            </p>

            <div className="flex gap-2 mt-5">
              <button
                onClick={() => { setDuplicating(null); setDupName(""); }}
                className="flex-1 py-2 rounded-xl border border-surface-border text-gray-400 text-sm hover:text-white transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={submitDuplicate}
                disabled={!dupName.trim() || dupMutation.isPending}
                className="flex-1 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {dupMutation.isPending ? (
                  <><Loader2 size={14} className="animate-spin" /> Duplicando…</>
                ) : (
                  <><Copy size={14} /> Duplicar</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function CampaignsPage() {
  return (
    <Suspense fallback={<div className="text-gray-500 py-8 text-center">Carregando...</div>}>
      <CampaignsInner />
    </Suspense>
  );
}
