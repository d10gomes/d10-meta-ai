-- Migration 006: Media Assets (Creative Library)
-- Apply via Supabase SQL editor on project kqdyowpmjsdxttxbcxoz

-- 1. Media asset types
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'media_type') THEN
    CREATE TYPE media_type AS ENUM ('image','video','gif');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'media_format') THEN
    CREATE TYPE media_format AS ENUM ('feed','story','reels','carousel','unknown');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'media_status') THEN
    CREATE TYPE media_status AS ENUM ('uploading','ready','synced_meta','error','deleted');
  END IF;
END
$$;

-- 2. media_assets table
CREATE TABLE IF NOT EXISTS media_assets (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    meta_account_id uuid REFERENCES meta_accounts(id),

    -- File info
    name            text NOT NULL,
    original_name   text NOT NULL,
    file_type       media_type NOT NULL,
    format          media_format NOT NULL DEFAULT 'unknown',
    mime_type       text NOT NULL,
    file_size_bytes bigint NOT NULL,
    width_px        int,
    height_px       int,
    duration_secs   numeric(8,2),  -- for videos

    -- Storage
    storage_bucket  text NOT NULL DEFAULT 'creatives',
    storage_path    text NOT NULL,
    public_url      text,

    -- Meta sync
    meta_image_hash text,   -- for images: hash returned by Meta
    meta_video_id   text,   -- for videos: video_id returned by Meta
    meta_status     text,   -- ACTIVE, DELETED, etc.
    meta_synced_at  timestamptz,

    -- Organisation
    offer_id        text,   -- brain offer reference
    tags            text[] DEFAULT '{}',
    notes           text,

    -- Performance (updated by Creative Agent)
    avg_ctr         numeric(6,4),
    avg_roas        numeric(8,4),
    avg_cpa         numeric(10,2),
    avg_frequency   numeric(6,3),
    times_used      int NOT NULL DEFAULT 0,
    last_used_at    timestamptz,
    performance_score numeric(4,1),  -- 0-10, set by Creative Agent

    status          media_status NOT NULL DEFAULT 'uploading',
    uploaded_by     uuid REFERENCES users(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_media_tenant       ON media_assets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_media_account      ON media_assets(meta_account_id);
CREATE INDEX IF NOT EXISTS idx_media_type         ON media_assets(file_type);
CREATE INDEX IF NOT EXISTS idx_media_status       ON media_assets(status);
CREATE INDEX IF NOT EXISTS idx_media_created_at   ON media_assets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_media_offer        ON media_assets(offer_id);

-- 3. Supabase Storage bucket (run this in Dashboard > Storage if not done via API)
-- INSERT INTO storage.buckets (id, name, public) VALUES ('creatives', 'creatives', true)
-- ON CONFLICT DO NOTHING;

-- 4. RLS
ALTER TABLE media_assets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation_media" ON media_assets
  USING (tenant_id IN (
    SELECT tenant_id FROM users WHERE id = auth.uid()
  ));
