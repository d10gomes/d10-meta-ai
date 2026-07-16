"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

function Field({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <p className="text-gray-500 text-xs uppercase mb-1">{label}</p>
      <p className="text-white">{value ?? "—"}</p>
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data: tenant } = useQuery({
    queryKey: ["tenant"],
    queryFn: () => api.get("/tenants/me").then((r) => r.data),
  });

  const [telegramId, setTelegramId] = useState<string>("");
  const [whatsapp, setWhatsapp] = useState<string>("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pre-fill once tenant loads
  const [prefilled, setPrefilled] = useState(false);
  if (tenant && !prefilled) {
    setTelegramId(tenant.telegram_chat_id ?? "");
    setWhatsapp(tenant.whatsapp_number ?? "");
    setPrefilled(true);
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      api.patch("/tenants/me/settings", {
        telegram_chat_id: telegramId.trim() || null,
        whatsapp_number: whatsapp.trim() || null,
      }).then((r) => r.data),
    onSuccess: () => {
      setSaved(true);
      setError(null);
      qc.invalidateQueries({ queryKey: ["tenant"] });
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-2xl font-bold">Configurações</h2>

      {/* Tenant info */}
      <div className="card space-y-4">
        <h3 className="font-semibold text-white">Minha Empresa</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <Field label="Nome" value={tenant?.name} />
          <Field label="Slug" value={tenant?.slug} />
          <Field label="Limite de Contas Meta" value={tenant?.max_meta_accounts ?? 15} />
          <Field label="Status" value={tenant?.is_active ? "Ativa" : "Inativa"} />
        </div>
      </div>

      {/* Notification settings */}
      <div className="card space-y-5">
        <div>
          <h3 className="font-semibold text-white">Notificações</h3>
          <p className="text-gray-400 text-sm mt-1">
            Receba relatórios diários e alertas críticos das suas campanhas.
          </p>
        </div>

        {/* Telegram */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300">
            Telegram — ID do Chat
          </label>
          <input
            type="text"
            value={telegramId}
            onChange={(e) => setTelegramId(e.target.value)}
            placeholder="Ex: 123456789"
            className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500"
          />
          <div className="bg-surface-card border border-surface-border rounded-lg p-3 text-xs text-gray-400 space-y-1">
            <p className="font-medium text-gray-300">Como obter seu Telegram Chat ID:</p>
            <p>1. Pesquise <span className="font-mono text-brand-400">@userinfobot</span> no Telegram</p>
            <p>2. Envie qualquer mensagem para ele</p>
            <p>3. Copie o número que aparecer em "Id:" e cole aqui</p>
            <p className="text-gray-500 pt-1">O bot do D10 precisa estar configurado no servidor para funcionar.</p>
          </div>
        </div>

        {/* WhatsApp */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300">
            WhatsApp — Número com DDD
          </label>
          <input
            type="text"
            value={whatsapp}
            onChange={(e) => setWhatsapp(e.target.value)}
            placeholder="Ex: 5511999998888"
            className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500"
          />
          <p className="text-xs text-gray-500">
            Formato: código do país + DDD + número (sem espaços ou traços). Requer Evolution API configurada.
          </p>
        </div>

        {/* Save button */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="btn-primary text-sm"
          >
            {saveMutation.isPending ? "Salvando..." : "Salvar notificações"}
          </button>
          {saved && (
            <span className="text-green-400 text-sm">✅ Salvo com sucesso</span>
          )}
          {error && (
            <span className="text-red-400 text-sm">Erro: {error}</span>
          )}
        </div>
      </div>

      {/* Current notification status */}
      <div className="card text-sm space-y-2">
        <h3 className="font-semibold text-white">Status das notificações</h3>
        <div className="flex items-center gap-2">
          <span>{tenant?.telegram_chat_id ? "🟢" : "⚪"}</span>
          <span className="text-gray-300">Telegram:</span>
          <span className="font-mono text-gray-400">{tenant?.telegram_chat_id ?? "Não configurado"}</span>
        </div>
        <div className="flex items-center gap-2">
          <span>{tenant?.whatsapp_number ? "🟢" : "⚪"}</span>
          <span className="text-gray-300">WhatsApp:</span>
          <span className="font-mono text-gray-400">{tenant?.whatsapp_number ?? "Não configurado"}</span>
        </div>
        <p className="text-xs text-gray-500 pt-1">
          Os relatórios são enviados automaticamente todo dia às 8h da manhã.
        </p>
      </div>
    </div>
  );
}
