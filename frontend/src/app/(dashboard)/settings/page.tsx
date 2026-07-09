"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const { data: tenant } = useQuery({
    queryKey: ["tenant"],
    queryFn: () => api.get("/tenants/me").then((r) => r.data),
  });

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-2xl font-bold">Configurações</h2>

      <div className="card space-y-4">
        <h3 className="font-semibold">Minha Empresa</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-500 text-xs uppercase mb-1">Nome</p>
            <p className="text-white">{tenant?.name || "—"}</p>
          </div>
          <div>
            <p className="text-gray-500 text-xs uppercase mb-1">Slug</p>
            <p className="text-white font-mono">{tenant?.slug || "—"}</p>
          </div>
          <div>
            <p className="text-gray-500 text-xs uppercase mb-1">Limite de Contas Meta</p>
            <p className="text-white">{tenant?.max_meta_accounts || 15}</p>
          </div>
          <div>
            <p className="text-gray-500 text-xs uppercase mb-1">Status</p>
            <span className={tenant?.is_active ? "badge-winner" : "badge-loser"}>
              {tenant?.is_active ? "Ativa" : "Inativa"}
            </span>
          </div>
        </div>
      </div>

      <div className="card space-y-3">
        <h3 className="font-semibold">Scheduler Automático</h3>
        <div className="text-sm text-gray-400 space-y-2">
          <p>🔄 <strong className="text-white">Scanner Agent</strong> — a cada 30 minutos</p>
          <p>🩺 <strong className="text-white">Doctor Agent</strong> — a cada 60 minutos</p>
          <p>⚡ <strong className="text-white">Executor Agent</strong> — a cada 10 minutos</p>
          <p>📱 <strong className="text-white">WhatsApp Report</strong> — todos os dias às 08:00</p>
        </div>
      </div>

      <div className="card space-y-3">
        <h3 className="font-semibold">Limites do Sistema</h3>
        <div className="text-sm text-gray-400 space-y-2">
          <p>📊 Suporte inicial: <strong className="text-white">15 contas Meta Ads</strong></p>
          <p>🚀 Capacidade máxima: <strong className="text-white">100+ contas Meta Ads</strong></p>
          <p>🏢 Arquitetura <strong className="text-white">Multi-tenant</strong> (empresas isoladas)</p>
          <p>🔐 Controle de acesso por <strong className="text-white">roles</strong> (admin / manager / viewer)</p>
        </div>
      </div>
    </div>
  );
}
