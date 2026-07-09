export interface MetaAccount {
  id: string;
  ad_account_id: string;
  name: string | null;
  is_active: boolean;
  last_synced_at: string | null;
}

export interface Campaign {
  id: string;
  meta_campaign_id: string;
  name: string | null;
  status: string | null;
  objective: string | null;
  daily_budget: number | null;
}

export interface Diagnosis {
  id: string;
  entity_type: string | null;
  entity_id: string | null;
  issue_type: string;
  severity: "low" | "medium" | "high" | "critical";
  details: Record<string, unknown> | null;
  resolved: boolean;
  created_at: string;
}

export interface AgentAction {
  id: string;
  action_type: string;
  entity_type: string | null;
  entity_id: string | null;
  status: "pending" | "executed" | "failed" | "skipped";
  executed_at: string | null;
  created_at: string;
}

export interface CreativeRanking {
  meta_ad_id: string;
  name: string;
  creative_id: string | null;
  creative_type: string | null;
  avg_ctr: number;
  avg_cpa: number;
  avg_roas: number;
  total_spend: number;
  total_conversions: number;
  score: number;
  tier: "winner" | "average" | "loser";
}

export interface ReportSummary {
  period_days: number;
  spend: number;
  clicks: number;
  impressions: number;
  conversions: number;
  revenue: number;
  ctr: number;
  cpa: number;
  roas: number;
  cpm: number;
  frequency: number;
}

export interface TimelinePoint {
  day: string;
  spend: number;
  conversions: number;
  roas: number;
}
