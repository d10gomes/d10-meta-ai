-- Migration 005: Phase 2 — Maestro, Simulation, Audit, Learning
-- Apply via Supabase SQL editor on project kqdyowpmjsdxttxbcxoz

-- 1. Extend agent_actions with simulation/approval columns
ALTER TABLE agent_actions
  ADD COLUMN IF NOT EXISTS simulation_result  jsonb,
  ADD COLUMN IF NOT EXISTS requires_approval  boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS approved_by        uuid REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS approved_at        timestamptz;

-- Extend status enum
ALTER TYPE action_status ADD VALUE IF NOT EXISTS 'simulating';
ALTER TYPE action_status ADD VALUE IF NOT EXISTS 'approved';
ALTER TYPE action_status ADD VALUE IF NOT EXISTS 'rejected';

-- 2. Audit log (imutável — nunca DELETE ou UPDATE aqui)
CREATE TABLE IF NOT EXISTS audit_logs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL REFERENCES tenants(id),
    agent_name    text NOT NULL,
    action_type   text NOT NULL,
    entity_type   text NOT NULL,
    entity_id     text,
    before_state  jsonb DEFAULT '{}'::jsonb,
    after_state   jsonb DEFAULT '{}'::jsonb,
    payload       jsonb DEFAULT '{}'::jsonb,
    cost_usd      numeric(10,6) DEFAULT 0,
    duration_ms   int,
    status        text NOT NULL DEFAULT 'success',
    error         text,
    executed_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_agent    ON audit_logs(tenant_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_audit_action_type     ON audit_logs(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_executed_at     ON audit_logs(executed_at DESC);

-- 3. Simulations
CREATE TYPE IF NOT EXISTS risk_level AS ENUM ('low','medium','high','critical');

CREATE TABLE IF NOT EXISTS simulations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id           uuid NOT NULL REFERENCES agent_actions(id),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    risk_level          risk_level NOT NULL DEFAULT 'medium',
    can_proceed         boolean NOT NULL DEFAULT true,
    impact_estimate     jsonb,
    risk_factors        jsonb,
    rollback_plan       jsonb,
    recommendation      text,
    confidence          numeric(4,3) DEFAULT 0.7,
    requires_approval   boolean NOT NULL DEFAULT false,
    approved_by         uuid REFERENCES users(id),
    approved_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_simulations_action    ON simulations(action_id);
CREATE INDEX IF NOT EXISTS idx_simulations_tenant    ON simulations(tenant_id);

-- 4. Orchestrations (Maestro runs)
CREATE TABLE IF NOT EXISTS orchestrations (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL REFERENCES tenants(id),
    objective        text NOT NULL,
    plan             jsonb,
    results          jsonb,
    status           text NOT NULL DEFAULT 'running',
    tasks_total      int DEFAULT 0,
    tasks_ok         int DEFAULT 0,
    tasks_failed     int DEFAULT 0,
    duration_seconds numeric(8,2),
    report           text,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz
);

CREATE INDEX IF NOT EXISTS idx_orchestrations_tenant ON orchestrations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_orchestrations_status ON orchestrations(status);

-- 5. Lessons (Learning Agent output)
CREATE TYPE IF NOT EXISTS lesson_type AS ENUM (
    'what_works','what_fails','audience_insight','creative_insight','budget_insight'
);

CREATE TABLE IF NOT EXISTS lessons (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid REFERENCES tenants(id),
    lesson_type   lesson_type NOT NULL,
    title         text NOT NULL,
    lesson        text NOT NULL,
    evidence      jsonb,
    context       jsonb,
    confidence    numeric(4,3) DEFAULT 0.7,
    applies_to    jsonb,
    applied_count int NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lessons_type       ON lessons(lesson_type);
CREATE INDEX IF NOT EXISTS idx_lessons_tenant     ON lessons(tenant_id);
CREATE INDEX IF NOT EXISTS idx_lessons_created_at ON lessons(created_at DESC);

-- 6. Tenant: add whatsapp_number and automation_level if not present
ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS whatsapp_number   text,
  ADD COLUMN IF NOT EXISTS automation_level  int NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS plan              text NOT NULL DEFAULT 'starter';
