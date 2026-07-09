-- Migration 004: Agent Memory + Knowledge Base tables
-- Run once in Supabase SQL Editor

-- Memory type enum
DO $$ BEGIN
  CREATE TYPE memory_type AS ENUM ('observation','decision','outcome','learning','context');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Knowledge type enum
DO $$ BEGIN
  CREATE TYPE knowledge_type AS ENUM (
    'raw_data','trend','insight','recommendation',
    'alert','report','decision','outcome'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Agent Memory table
CREATE TABLE IF NOT EXISTS agent_memory (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name    VARCHAR(80)  NOT NULL,
  tenant_id     UUID         NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  memory_type   memory_type  NOT NULL DEFAULT 'observation',
  key           VARCHAR(200) NOT NULL,
  content       JSONB        NOT NULL DEFAULT '{}',
  importance    INTEGER      NOT NULL DEFAULT 5,
  recall_count  INTEGER      NOT NULL DEFAULT 0,
  last_recalled_at TIMESTAMPTZ,
  expires_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (agent_name, tenant_id, key)
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_agent ON agent_memory(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_memory_tenant ON agent_memory(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_memory_key ON agent_memory(key);

-- Knowledge Base table
CREATE TABLE IF NOT EXISTS knowledge_base (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID         NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  source_agent  VARCHAR(80)  NOT NULL,
  entry_type    knowledge_type NOT NULL,
  topic         VARCHAR(200) NOT NULL,
  content       JSONB        NOT NULL DEFAULT '{}',
  summary       TEXT,
  confidence    FLOAT        NOT NULL DEFAULT 0.8,
  consumed_by   JSONB        NOT NULL DEFAULT '[]',
  expires_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_tenant ON knowledge_base(tenant_id);
CREATE INDEX IF NOT EXISTS idx_kb_source ON knowledge_base(source_agent);
CREATE INDEX IF NOT EXISTS idx_kb_topic ON knowledge_base(topic);
CREATE INDEX IF NOT EXISTS idx_kb_created ON knowledge_base(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_type ON knowledge_base(entry_type);
