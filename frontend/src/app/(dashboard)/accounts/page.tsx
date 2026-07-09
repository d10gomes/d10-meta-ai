"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { MetaAccount } from "@/types";
import { Plus, Trash2, RefreshCw, CheckCircle, XCircle, Loader2, Facebook, Key } from "lucide-react";

interface AdAccountInfo {
  account_id: string;
  name: string;
  status: number;
  currency: string;
  timezone: string;
  business_name?: string;
}

interface ValidateResponse {
  valid: boolean;
  user_name?: string;
  user_id?: string;
  ad_accounts: AdAccountInfo[];
  error?: string;
}

type ConnectMode = "idle" | "oauth" | "manual";

function AccountsPageInner() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<ConnectMode>("idle");

  // Manual token flow state
  const [manualToken, setManualToken] = useState("");
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<ValidateResponse | null>(null);
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(new Set());

  // OAuth callback — token chegou via URL
  const oauthToken = searchParams.get("oauth_token");
  const oauthError = searchParams.get("oauth_error");

  useEffect(() => {
    if (oauthToken) {
      setManualToken(oauthToken);
      setMode("manual");
      handleValidateToken(oauthToken);
      // Limpa a URL
      window.history.replaceState({}, "", "/accounts");
    }
  }, [oauthToken]);

  const { data: accounts, isLoading } = useQuery<MetaAccount[]>({
    queryKey: ["meta-accounts"],
    queryFn: () => api.get("/meta-accounts").then((r) => r.data),
  });

  const [toast, setToast] = useState<string | null>(null);
  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 4000); };

  const scan = useMutation({
    mutationFn: () => api.post("/agents/scan"),
    onSuccess: () => showToast("Sincronização iniciada! Aguarde alguns minutos."),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/meta-accounts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meta-accounts"] }),
  });

  const connectAccounts = useMutation({
    mutationFn: (payload: { access_token: string; accounts: { account_id: string; name: string }[] }) =>
      api.post("/meta-accounts/connect-from-token", payload),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["meta-accounts"] });
      const data = res.data;
      showToast(`✅ ${data.created.length} conta(s) conectada(s)! Token: ${data.token_type === "long_lived" ? "Long-lived (60 dias)" : "Short-lived"}`);
      setMode("idle");
      setManualToken("");
      setValidateResult(null);
      setSelectedAccounts(new Set());
    },
    onError: (err: any) => {
      alert("Erro ao conectar: " + (err.response?.data?.detail || err.message));
    },
  });

  const handleValidateToken = async (token?: string) => {
    const t = token || manualToken;
    if (!t.trim()) return;
    setValidating(true);
    setValidateResult(null);
    try {
      const res = await api.post("/meta-accounts/validate-token", { access_token: t });
      setValidateResult(res.data);
      if (res.data.valid && res.data.ad_accounts.length > 0) {
        // Pré-seleciona todas as contas encontradas
        setSelectedAccounts(new Set(res.data.ad_accounts.map((a: AdAccountInfo) => a.account_id)));
      }
    } catch {
      setValidateResult({ valid: false, error: "Erro ao conectar com a API do Facebook", ad_accounts: [] });
    } finally {
      setValidating(false);
    }
  };

  const handleOAuthConnect = async () => {
    try {
      const res = await api.get("/meta-accounts/oauth/url");
      window.location.href = res.data.oauth_url;
    } catch (err: any) {
      alert("Erro: " + (err.response?.data?.detail || "Configure o META_APP_ID no .env primeiro"));
    }
  };

  const handleConnectSelected = () => {
    if (!validateResult?.valid || selectedAccounts.size === 0) return;
    const accounts = validateResult.ad_accounts
      .filter((a) => selectedAccounts.has(a.account_id))
      .map((a) => ({ account_id: a.account_id, name: a.name }));
    connectAccounts.mutate({ access_token: manualToken, accounts });
  };

  const toggleAccount = (id: string) => {
    setSelectedAccounts((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });
  };

  const statusBadge = (status: number) => {
    const map: Record<number, [string, string]> = {
      1: ["Ativa", "badge-winner"],
      2: ["Desativada", "badge-loser"],
      3: ["Sem Pagamento", "badge-loser"],
      7: ["Encerrada", "badge-low"],
      9: ["Pendente", "badge-medium"],
    };
    const [label, cls] = map[status] || ["Desconhecido", "badge-medium"];
    return <span className={cls}>{label}</span>;
  };

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-green-600 text-white px-5 py-3 rounded-lg shadow-lg text-sm">
          {toast}
        </div>
      )}
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Contas Meta Ads</h2>
          <p className="text-gray-400 text-sm mt-1">{accounts?.length ?? 0} conta(s) conectada(s)</p>
        </div>
        <div className="flex gap-3">
          {accounts && accounts.length > 0 && (
            <button
              onClick={() => scan.mutate()}
              disabled={scan.isPending}
              className="btn-ghost flex items-center gap-2 text-sm"
            >
              {scan.isPending ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
              Sincronizar
            </button>
          )}
          {mode === "idle" && (
            <div className="flex gap-2">
              <button
                onClick={handleOAuthConnect}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg transition-colors text-sm"
              >
                <Facebook size={16} /> Conectar com Facebook
              </button>
              <button
                onClick={() => setMode("manual")}
                className="btn-ghost flex items-center gap-2 text-sm border border-surface-border"
              >
                <Key size={16} /> Token Manual
              </button>
            </div>
          )}
          {mode !== "idle" && (
            <button onClick={() => { setMode("idle"); setValidateResult(null); setManualToken(""); }} className="btn-ghost text-sm">
              Cancelar
            </button>
          )}
        </div>
      </div>

      {/* OAuth Error Banner */}
      {oauthError && (
        <div className="card border border-red-500/30 bg-red-500/10">
          <p className="text-red-400 text-sm">❌ Erro no login com Facebook: {oauthError}</p>
        </div>
      )}

      {/* Manual Token Form */}
      {mode === "manual" && (
        <div className="card space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Key size={18} className="text-brand-500" />
            <h3 className="font-semibold">Conectar via Access Token</h3>
          </div>

          <div className="bg-surface border border-surface-border rounded-lg p-4 text-sm text-gray-400 space-y-2">
            <p className="font-medium text-white">Como obter seu token:</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Acesse <a href="https://business.facebook.com/settings/system-users" target="_blank" rel="noopener noreferrer" className="text-brand-500 hover:underline">Meta Business Manager → Usuários do Sistema</a></li>
              <li>Crie um usuário do sistema com role <strong className="text-white">Admin</strong></li>
              <li>Clique em <strong className="text-white">Gerar token</strong> e selecione permissões: <code className="text-brand-500">ads_read, ads_management, read_insights</code></li>
              <li>Cole o token abaixo — vamos detectar suas contas automaticamente</li>
            </ol>
            <p className="text-xs text-gray-500 mt-2">
              💡 Ou use o <strong className="text-white">Graph API Explorer</strong>:{" "}
              <a href="https://developers.facebook.com/tools/explorer" target="_blank" rel="noopener noreferrer" className="text-brand-500 hover:underline">
                developers.facebook.com/tools/explorer
              </a>
            </p>
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase mb-1 block">Access Token</label>
            <textarea
              rows={3}
              value={manualToken}
              onChange={(e) => { setManualToken(e.target.value); setValidateResult(null); }}
              placeholder="EAAxxxxxxxxxxxxxxx..."
              className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm font-mono focus:outline-none focus:border-brand-500 resize-none"
            />
          </div>

          <div className="flex gap-3 items-center">
            <button
              onClick={() => handleValidateToken()}
              disabled={!manualToken.trim() || validating}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              {validating ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
              Validar Token
            </button>
            {validateResult && !validateResult.valid && (
              <span className="text-red-400 text-sm flex items-center gap-1">
                <XCircle size={16} /> {validateResult.error}
              </span>
            )}
          </div>

          {/* Resultado da validação */}
          {validateResult?.valid && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-green-400 text-sm">
                <CheckCircle size={16} />
                Token válido — conectado como <strong>{validateResult.user_name}</strong>
                {" "}({validateResult.ad_accounts.length} conta(s) encontrada(s))
              </div>

              {validateResult.ad_accounts.length === 0 ? (
                <p className="text-gray-500 text-sm">Nenhuma Ad Account encontrada neste token.</p>
              ) : (
                <>
                  <p className="text-xs text-gray-400 uppercase tracking-wider">Selecione as contas para conectar:</p>
                  <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                    {validateResult.ad_accounts.map((acc) => (
                      <label
                        key={acc.account_id}
                        className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                          selectedAccounts.has(acc.account_id)
                            ? "border-brand-500 bg-brand-500/10"
                            : "border-surface-border hover:border-gray-500"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedAccounts.has(acc.account_id)}
                          onChange={() => toggleAccount(acc.account_id)}
                          className="accent-brand-500"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-white text-sm font-medium truncate">{acc.name}</span>
                            {statusBadge(acc.status)}
                          </div>
                          <div className="text-xs text-gray-500 mt-0.5 flex gap-3">
                            <span>ID: act_{acc.account_id}</span>
                            <span>{acc.currency}</span>
                            <span>{acc.timezone}</span>
                            {acc.business_name && <span>📁 {acc.business_name}</span>}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>

                  <div className="flex items-center gap-3 pt-2">
                    <button
                      onClick={handleConnectSelected}
                      disabled={selectedAccounts.size === 0 || connectAccounts.isPending}
                      className="btn-primary flex items-center gap-2 text-sm"
                    >
                      {connectAccounts.isPending ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Plus size={16} />
                      )}
                      Conectar {selectedAccounts.size} conta(s)
                    </button>
                    <span className="text-xs text-gray-500">
                      O token será convertido para long-lived (60 dias)
                    </span>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Lista de contas conectadas */}
      {isLoading ? (
        <div className="card flex items-center gap-3 text-gray-500">
          <Loader2 size={18} className="animate-spin" /> Carregando contas...
        </div>
      ) : accounts && accounts.length === 0 ? (
        <div className="card text-center py-12">
          <Facebook size={40} className="mx-auto text-gray-600 mb-4" />
          <p className="text-gray-400 font-medium">Nenhuma conta Meta Ads conectada</p>
          <p className="text-gray-600 text-sm mt-1">Use o botão acima para conectar sua primeira conta</p>
        </div>
      ) : (
        <div className="card">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-surface-border text-left">
                <th className="pb-3 pr-4">Nome</th>
                <th className="pb-3 pr-4">Ad Account ID</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3">Última sincronização</th>
                <th className="pb-3" />
              </tr>
            </thead>
            <tbody>
              {accounts?.map((a) => (
                <tr key={a.id} className="border-b border-surface-border last:border-0 hover:bg-surface-border/20 transition-colors">
                  <td className="py-3 pr-4 text-white font-medium">{a.name || "—"}</td>
                  <td className="py-3 pr-4 text-gray-400 font-mono text-xs">act_{a.ad_account_id}</td>
                  <td className="py-3 pr-4">
                    <span className={a.is_active ? "badge-winner" : "badge-loser"}>
                      {a.is_active ? "Ativa" : "Inativa"}
                    </span>
                  </td>
                  <td className="py-3 text-gray-400 text-xs">
                    {a.last_synced_at
                      ? new Date(a.last_synced_at).toLocaleString("pt-BR")
                      : <span className="text-yellow-500">Nunca sincronizada</span>}
                  </td>
                  <td className="py-3 text-right">
                    <button
                      onClick={() => remove.mutate(a.id)}
                      className="text-gray-500 hover:text-red-400 transition-colors"
                      title="Remover conta"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function AccountsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-500">Carregando...</div>}>
      <AccountsPageInner />
    </Suspense>
  );
}
