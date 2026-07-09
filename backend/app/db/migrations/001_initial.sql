-- D10 META AI — Initial Schema Migration
-- Run this against your Supabase (PostgreSQL) project

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enums
CREATE TYPE user_role AS ENUM ('admin', 'manager', 'viewer');
CREATE TYPE action_status AS ENUM ('pending', 'executed', 'failed', 'skipped');
CREATE TYPE severity_level AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE report_status AS ENUM ('sent', 'failed', 'pending');

-- Tenants (multi-company)
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(200) NOT NULL,
    slug        VARCHAR(100) NOT NULL UNIQUE,
    is_active   BOOLEAN DEFAULT TRUE,
    max_meta_accounts INTEGER DEFAULT 15,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    name            VARCHAR(200),
    role            user_role DEFAULT 'viewer',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, email)
);

-- Meta Ads Accounts
CREATE TABLE meta_accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ad_account_id   VARCHAR(100) NOT NULL,
    name            VARCHAR(200),
    access_token    TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    last_synced_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, ad_account_id)
);

-- Campaigns
CREATE TABLE campaigns (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meta_account_id     UUID NOT NULL REFERENCES meta_accounts(id) ON DELETE CASCADE,
    meta_campaign_id    VARCHAR(100) NOT NULL UNIQUE,
    name                VARCHAR(500),
    objective           VARCHAR(100),
    status              VARCHAR(50),
    daily_budget        NUMERIC(12,2),
    lifetime_budget     NUMERIC(12,2),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Ad Sets
CREATE TABLE adsets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    meta_adset_id   VARCHAR(100) NOT NULL UNIQUE,
    name            VARCHAR(500),
    status          VARCHAR(50),
    daily_budget    NUMERIC(12,2),
    targeting       JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Ads
CREATE TABLE ads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    adset_id        UUID NOT NULL REFERENCES adsets(id) ON DELETE CASCADE,
    meta_ad_id      VARCHAR(100) NOT NULL UNIQUE,
    name            VARCHAR(500),
    status          VARCHAR(50),
    creative_id     VARCHAR(100),
    creative_type   VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Ad Metrics (daily snapshots)
CREATE TABLE ad_metrics (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ad_id           UUID NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    impressions     INTEGER DEFAULT 0,
    clicks          INTEGER DEFAULT 0,
    spend           NUMERIC(12,4) DEFAULT 0,
    conversions     INTEGER DEFAULT 0,
    revenue         NUMERIC(12,4) DEFAULT 0,
    ctr             NUMERIC(8,4),
    cpc             NUMERIC(8,4),
    cpm             NUMERIC(8,4),
    cpa             NUMERIC(12,4),
    roas            NUMERIC(8,4),
    frequency       NUMERIC(8,4),
    reach           INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ad_id, date)
);

-- Agent Events (audit log)
CREATE TABLE agent_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_type  VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id   VARCHAR(100),
    payload     JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Actions
CREATE TABLE agent_actions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    action_type VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id   VARCHAR(100),
    payload     JSONB,
    status      action_status DEFAULT 'pending',
    executed_at TIMESTAMPTZ,
    error       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Diagnoses
CREATE TABLE diagnoses (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    entity_type VARCHAR(50),
    entity_id   VARCHAR(100),
    issue_type  VARCHAR(100) NOT NULL,
    severity    severity_level DEFAULT 'medium',
    details     JSONB,
    resolved    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- WhatsApp Reports
CREATE TABLE whatsapp_reports (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    phone_number VARCHAR(30) NOT NULL,
    report_type VARCHAR(100),
    content     TEXT,
    status      report_status DEFAULT 'pending',
    sent_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance at scale (100+ accounts)
CREATE INDEX idx_meta_accounts_tenant ON meta_accounts(tenant_id);
CREATE INDEX idx_campaigns_account ON campaigns(meta_account_id);
CREATE INDEX idx_adsets_campaign ON adsets(campaign_id);
CREATE INDEX idx_ads_adset ON ads(adset_id);
CREATE INDEX idx_ad_metrics_ad_date ON ad_metrics(ad_id, date DESC);
CREATE INDEX idx_diagnoses_tenant_resolved ON diagnoses(tenant_id, resolved);
CREATE INDEX idx_actions_tenant_status ON agent_actions(tenant_id, status);
CREATE INDEX idx_events_tenant_type ON agent_events(tenant_id, event_type);

-- Row Level Security (Supabase multi-tenant isolation)
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE adsets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ads ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE diagnoses ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_reports ENABLE ROW LEVEL SECURITY;
