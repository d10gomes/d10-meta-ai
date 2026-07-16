"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AGENT_NAMES, AGENT_DESCRIPTIONS } from "@/lib/labels";
import { Scan, Stethoscope, Zap, MessageCircle, Clock, CheckCircle2, XCircle, Loader2, Play, RefreshCw, Brain, DollarSign, Target, ChevronDown, ChevronUp } from "lucide-react";

type AgentStatus = {
  id: string;
  name: string;
  description: string;
  icon: string;
  schedule: string;
  cron: string;
  category: string;
  next_run: string | null;
  last_run: {
    started_at: string | null;
    finished_at: string | null;
    status: string;
    duration_seconds: number | null;
    items_processed: number | null;
    error: string | null;
    trigger: string | null;
  } | null;
};

type AgentRun = {
  id: string;
  agent_name: string;
  trigger: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  items_processed: number | null;
  error: string | null;
};

type AgentInsight = {
  id: string;
  agent_name: string;
  title: string;
  summary: string;
  details: Record<string, unknown>;
  actions_taken: number;
  created_at: string;
};

const ICON_MAP: Record<string, React.ReactNode> = {
  scanner: <Scan size={20} />,
  doctor: <Stethoscope size={20} />,
  executor: <Zap size={20} />,
  whatsapp: <MessageCircle size={20} />,
  analyst: <Brain size={20} />,
  budget_optimizer: <DollarSign size={20} />,
  campaign_manager: <Target size={20} />,
};

const TRIGGER_ENDPOINT: Record<string, string> = {
  scanner: "/agents/scan",
  doctor: "/agents/doctor",
  executor: "/agents/execute",
  whatsapp: "/agents/report/whatsapp",
  analyst: "/agents/analyze",
  budget_optimizer: "/agents/optimize-budget",
};

const STATUS_CONFIG: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  success: {
    label: "Último: OK",
    icon: <CheckCircle2 size={12} />,
    color: "text-green-400",
  },
  failed: {
    label: "Último: Falhou",
    icon: <XCircle size={12} />,
    color: "text-red-400",
  },
  running: {
    label: "Executando agora",
    icon: <Loader2 size={12} className="animate-spin" />,
    color: "text-yellow-400",
  },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status];
  if (!cfg) return <span className="text-gray-500 text-xs">Nunca executou</span>;
  return (
    <span className={`flex items-center gap-1 text-xs font-medium ${cfg.color}`}>
      {cfg.icon} {cfg.label}
    </span>
  );
}

function formatDuration(secs: number | null) {
  if (!secs) return "—";
  if (secs < 60) return `${secs.toFixed(0)}s`;
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export default function AgentsPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [expandedInsight, setExpandedInsight] = useState<string | null>(null);
  const qc = useQueryClient();

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const { data: statusData, isLoading } = useQuery({
    queryKey: ["agents-status"],
    queryFn: () => api.get("/agents/status").then((r) => r.data),
    refetchInterval: 15000,
  });

  const { data: runsData } = useQuery({
    queryKey: ["agent-runs", selectedAgent],
    queryFn: () =>
      api
        .get("/agents/runs", { params: { agent: selectedAgent || undefined, limit: 20 } })
        .then((r) => r.data),
    refetchInterval: 15000,
  });

  const { data: insightsData } = useQuery({
    queryKey: ["agent-insights"],
    queryFn: () => api.get("/agents/insights?limit=10").then((r) => r.data),
    refetchInterval: 30000,
  });

  const trigger = useMutation({
    mutationFn: (agentId: string) => api.post(TRIGGER_ENDPOINT[agentId]),
    onSuccess: (_, agentId) => {
      showToast(`${AGENT_NAMES[agentId] || agentId} iniciado! Aguarde alguns minutos.`);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["agents-status"] });
        qc.invalidateQueries({ queryKey: ["agent-runs"] });
      }, 3000);
    },
    onError: () => showToast("Erro ao iniciar agente."),
  });

  const agents: AgentStatus[] = statusData?.agents ?? [];

  const agentName = (a: AgentStatus) => AGENT_NAMES[a.id] || a.name;
  const agentDescription = (a: AgentStatus) => AGENT_DESCRIPTIONS[a.id] || a.description;

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-green-600 text-white px-5 py-3 rounded-lg shadow-lg text-sm">
          {toast}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Agentes Automáticos</h2>
          <p className="text-gray-400 text-sm mt-1">
            {statusData?.scheduler_running
              ? "✅ Sistema ativo — agentes trabalham automaticamente para você"
              : "⚠️ Sistema pausado"}
          </p>
        </div>
        <button
          onClick={() => {
            qc.invalidateQueries({ queryKey: ["agents-status"] });
            qc.invalidateQueries({ queryKey: ["agent-runs"] });
          }}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw size={14} /> Atualizar
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-40 text-gray-500">
          <Loader2 size={24} className="animate-spin mr-2" /> Carregando agentes...
        </div>
      ) : (
        <>
          {/* Specialist agents */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
              <Brain size={11} /> Agentes Especialistas
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {agents.filter((a) => a.category === "specialist").map((agent) => (
                <div
                  key={agent.id}
                  className={`card cursor-pointer border transition-colors ${
                    selectedAgent === agent.id ? "border-brand-500" : "border-transparent hover:border-gray-600"
                  }`}
                  onClick={() => setSelectedAgent(selectedAgent === agent.id ? null : agent.id)}
                >
                  <div className="flex items-start gap-3">
                    <div className="bg-brand-500/10 p-2.5 rounded-xl text-brand-500 flex-shrink-0">
                      {ICON_MAP[agent.id]}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="font-semibold text-white text-sm">{agentName(agent)}</h3>
                        <StatusBadge status={agent.last_run?.status ?? "never"} />
                      </div>
                      <p className="text-xs text-gray-400 mt-1">{agentDescription(agent)}</p>
                      <div className="mt-2 text-xs text-gray-500 space-y-0.5">
                        <div className="flex items-center gap-1"><Clock size={10} /> {agent.schedule}</div>
                        <div>Próxima execução: <span className="text-gray-300">{formatDate(agent.next_run)}</span></div>
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-end mt-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); trigger.mutate(agent.id); }}
                      disabled={trigger.isPending || !TRIGGER_ENDPOINT[agent.id]}
                      className="btn-primary text-xs flex items-center gap-1"
                    >
                      <Play size={12} /> Executar agora
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Infra agents */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
              <Zap size={11} /> Agentes de Suporte
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {agents.filter((a) => a.category !== "specialist").map((agent) => (
                <div
                  key={agent.id}
                  className={`card cursor-pointer border transition-colors ${
                    selectedAgent === agent.id
                      ? "border-brand-500"
                      : "border-transparent hover:border-gray-600"
                  }`}
                  onClick={() => setSelectedAgent(selectedAgent === agent.id ? null : agent.id)}
                >
                  <div className="flex items-start gap-4">
                    <div className="bg-brand-500/10 p-3 rounded-xl text-brand-500 flex-shrink-0">
                      {ICON_MAP[agent.id]}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="font-semibold text-white">{agentName(agent)}</h3>
                        <StatusBadge status={agent.last_run?.status ?? "never"} />
                      </div>
                      <p className="text-xs text-gray-400 mt-1">{agentDescription(agent)}</p>

                      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <Clock size={11} /> {agent.schedule}
                        </span>
                        <span>
                          Próxima: <span className="text-gray-300">{formatDate(agent.next_run)}</span>
                        </span>
                        <span>
                          Última: <span className="text-gray-300">{formatDate(agent.last_run?.started_at ?? null)}</span>
                        </span>
                        <span>
                          Duração: <span className="text-gray-300">{formatDuration(agent.last_run?.duration_seconds ?? null)}</span>
                        </span>
                        {agent.last_run?.items_processed != null && (
                          <span className="col-span-2">
                            Itens processados: <span className="text-gray-300">{agent.last_run.items_processed}</span>
                          </span>
                        )}
                        {agent.last_run?.error && (
                          <span className="col-span-2 text-red-400 truncate" title={agent.last_run.error}>
                            ⚠ {agent.last_run.error.slice(0, 80)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end mt-4">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        trigger.mutate(agent.id);
                      }}
                      disabled={trigger.isPending || !TRIGGER_ENDPOINT[agent.id]}
                      className="btn-primary text-xs flex items-center gap-1"
                    >
                      <Play size={12} /> Executar agora
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Agent insights */}
      {insightsData && insightsData.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold text-white flex items-center gap-2">
            <Brain size={16} className="text-brand-400" /> Últimos relatórios dos agentes
          </h3>
          {(insightsData as AgentInsight[]).map((insight) => (
            <div key={insight.id} className="card border border-gray-800">
              <div
                className="flex items-start justify-between cursor-pointer"
                onClick={() => setExpandedInsight(expandedInsight === insight.id ? null : insight.id)}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-brand-400 flex-shrink-0">{ICON_MAP[insight.agent_name]}</span>
                  <div className="min-w-0">
                    <p className="font-medium text-white text-sm truncate">{insight.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{insight.summary}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-4 flex-shrink-0">
                  {insight.actions_taken > 0 && (
                    <span className="text-xs bg-brand-500/10 text-brand-400 px-2 py-0.5 rounded-full">
                      {insight.actions_taken} ação(ões)
                    </span>
                  )}
                  <span className="text-xs text-gray-500">{formatDate(insight.created_at)}</span>
                  {expandedInsight === insight.id
                    ? <ChevronUp size={14} className="text-gray-500" />
                    : <ChevronDown size={14} className="text-gray-500" />
                  }
                </div>
              </div>
              {expandedInsight === insight.id && (
                <div className="mt-4 pt-4 border-t border-gray-800">
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap overflow-auto max-h-96 bg-gray-900 rounded p-3">
                    {JSON.stringify(insight.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Run history */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-white">
            Histórico de execuções
            {selectedAgent && (
              <span className="ml-2 text-brand-400 text-sm font-normal">
                — {AGENT_NAMES[selectedAgent] || selectedAgent}
              </span>
            )}
          </h3>
          {selectedAgent && (
            <button
              onClick={() => setSelectedAgent(null)}
              className="text-xs text-gray-500 hover:text-white"
            >
              Ver todos
            </button>
          )}
        </div>

        {!runsData || runsData.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-8">Nenhuma execução registrada ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-left pb-2 pr-4">Agente</th>
                  <th className="text-left pb-2 pr-4">Início</th>
                  <th className="text-left pb-2 pr-4">Duração</th>
                  <th className="text-left pb-2 pr-4">Itens</th>
                  <th className="text-left pb-2 pr-4">Tipo</th>
                  <th className="text-left pb-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {(runsData as AgentRun[]).map((run) => (
                  <tr key={run.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-2 pr-4 font-medium text-gray-300">
                      <span className="inline-flex items-center gap-1 text-brand-400">
                        {ICON_MAP[run.agent_name]}
                        <span className="text-gray-300 text-xs">{AGENT_NAMES[run.agent_name] || run.agent_name}</span>
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-400 text-xs">{formatDate(run.started_at)}</td>
                    <td className="py-2 pr-4 text-gray-400 text-xs">{formatDuration(run.duration_seconds)}</td>
                    <td className="py-2 pr-4 text-gray-400 text-xs">{run.items_processed ?? "—"}</td>
                    <td className="py-2 pr-4">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        run.trigger === "manual"
                          ? "bg-blue-500/10 text-blue-400"
                          : "bg-gray-700 text-gray-400"
                      }`}>
                        {run.trigger === "manual" ? "Manual" : "Automático"}
                      </span>
                    </td>
                    <td className="py-2">
                      <StatusBadge status={run.status} />
                      {run.error && (
                        <p className="text-red-400 text-xs mt-0.5 truncate max-w-xs" title={run.error}>
                          {run.error.slice(0, 60)}
                        </p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
