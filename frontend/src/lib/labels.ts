// Tradução de todos os termos técnicos para linguagem de negócio

export const OBJECTIVE_LABELS: Record<string, string> = {
  OUTCOME_SALES: "Vendas",
  OUTCOME_TRAFFIC: "Tráfego / Visitas",
  OUTCOME_LEADS: "Captação de Leads",
  OUTCOME_AWARENESS: "Reconhecimento de Marca",
  OUTCOME_ENGAGEMENT: "Engajamento",
  OUTCOME_APP_PROMOTION: "Instalações de App",
  LINK_CLICKS: "Cliques no Link",
  CONVERSIONS: "Conversões",
  REACH: "Alcance",
  BRAND_AWARENESS: "Reconhecimento de Marca",
  VIDEO_VIEWS: "Visualizações de Vídeo",
  MESSAGES: "Mensagens",
  STORE_VISITS: "Visitas à Loja",
  CATALOG_SALES: "Vendas pelo Catálogo",
};

export const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Ativa",
  PAUSED: "Pausada",
  DELETED: "Excluída",
  ARCHIVED: "Arquivada",
  IN_PROCESS: "Processando",
  WITH_ISSUES: "Com Problemas",
  PENDING_REVIEW: "Em Revisão",
};

export const SEVERITY_LABELS: Record<string, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Atenção",
  low: "Baixo",
};

export const ISSUE_LABELS: Record<string, string> = {
  high_cpa: "Custo por cliente muito alto",
  low_roas: "Retorno sobre investimento baixo",
  high_frequency: "Público vendo o mesmo anúncio muitas vezes (cansaço)",
  low_ctr: "Poucas pessoas clicando no anúncio",
  budget_underutilized: "Orçamento não está sendo usado totalmente",
  audience_saturation: "Público saturado — precisa de criativo novo",
  no_conversions: "Campanha sem nenhuma venda ou resultado",
  high_spend_no_result: "Gastando dinheiro sem resultado",
  creative_fatigue: "Criativo cansado — as pessoas pararam de clicar",
  bid_too_low: "Lance muito baixo — anúncio não está saindo",
  learning_phase: "Campanha em fase de aprendizado — aguardar",
  budget_limited: "Orçamento limitando o alcance da campanha",
};

export const ACTION_TYPE_LABELS: Record<string, string> = {
  pause_adset: "Pausar conjunto de anúncios com baixo desempenho",
  increase_budget: "Aumentar orçamento de campanha lucrativa",
  decrease_budget: "Reduzir orçamento de campanha com prejuízo",
  update_targeting: "Atualizar segmentação de público",
  duplicate_campaign: "Duplicar campanha de sucesso",
  pause_campaign: "Pausar campanha sem resultado",
  activate_campaign: "Ativar campanha pausada",
  update_bid: "Ajustar valor do lance",
  replace_creative: "Trocar criativo cansado",
};

export const AGENT_NAMES: Record<string, string> = {
  scanner: "Coletor de Dados",
  analyst: "Analista de Performance",
  doctor: "Diagnóstico de Campanhas",
  decision: "Motor de Decisões",
  executor: "Executor de Ações",
  budget_optimizer: "Otimizador de Orçamento",
  creative: "Analista de Criativos",
  whatsapp: "Relatório WhatsApp",
  maestro: "Maestro AI",
  performance_monitor: "Monitor 24 Horas",
};

export const AGENT_DESCRIPTIONS: Record<string, string> = {
  scanner: "Coleta dados das suas campanhas do Meta a cada 30 minutos e mantém tudo atualizado",
  analyst: "Analisa os resultados e identifica o que está funcionando e o que precisa melhorar",
  doctor: "Faz um diagnóstico completo das campanhas e aponta problemas com sugestões de solução",
  decision: "Decide quais ações tomar para melhorar os resultados com base nos dados coletados",
  executor: "Executa as ações aprovadas por você diretamente no Meta Ads",
  budget_optimizer: "Redistribui o orçamento automaticamente para as campanhas que estão trazendo mais resultado",
  creative: "Avalia quais imagens e vídeos estão performando melhor e quais precisam ser trocados",
  whatsapp: "Envia um resumo diário dos seus resultados direto no seu WhatsApp",
  maestro: "Coordena todos os agentes e executa estratégias complexas com um único comando",
  performance_monitor: "Monitora suas campanhas 24 horas e te avisa se algo sair do normal",
};

export function translateObjective(objective: string | null | undefined): string {
  if (!objective) return "—";
  return OBJECTIVE_LABELS[objective] || objective;
}

export function translateStatus(status: string | null | undefined): string {
  if (!status) return "—";
  return STATUS_LABELS[status] || status;
}

export function translateIssue(issue: string | null | undefined): string {
  if (!issue) return issue || "—";
  return ISSUE_LABELS[issue] || issue.replace(/_/g, " ");
}

export function translateAction(action: string | null | undefined): string {
  if (!action) return "—";
  return ACTION_TYPE_LABELS[action] || action.replace(/_/g, " ");
}

export function formatBudget(value: number | null | undefined): string {
  if (!value) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value / 100);
}

export function formatMoney(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("pt-BR").format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toFixed(2)}%`;
}
