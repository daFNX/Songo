BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_email_lowercase CHECK (email = lower(email)),
    CONSTRAINT users_email_length CHECK (length(email) BETWEEN 3 AND 254)
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique_idx ON users (email);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent_hash CHAR(64),
    CONSTRAINT auth_sessions_expiry CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS auth_sessions_user_active_idx
    ON auth_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    key_hash CHAR(64) PRIMARY KEY,
    window_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    locked_until TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS auth_rate_limits_window_idx
    ON auth_rate_limits (window_started_at);

CREATE TABLE IF NOT EXISTS authorized_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    source_url TEXT NOT NULL,
    license_name TEXT NOT NULL,
    authorization_reference TEXT NOT NULL,
    audio_fingerprint CHAR(64) NOT NULL,
    chroma_profile REAL[] NOT NULL,
    authorized BOOLEAN NOT NULL DEFAULT false,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT catalog_profile_length CHECK (cardinality(chroma_profile) = 12),
    CONSTRAINT catalog_provenance_nonempty CHECK (
        length(trim(title)) > 0
        AND length(trim(artist)) > 0
        AND length(trim(source_url)) > 0
        AND length(trim(license_name)) > 0
        AND length(trim(authorization_reference)) > 0
    )
);

CREATE INDEX IF NOT EXISTS authorized_catalog_fingerprint_idx
    ON authorized_catalog (audio_fingerprint)
    WHERE authorized IS TRUE;
CREATE INDEX IF NOT EXISTS authorized_catalog_authorized_idx
    ON authorized_catalog (created_at DESC)
    WHERE authorized IS TRUE;

CREATE TABLE IF NOT EXISTS analysis_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bpm SMALLINT NOT NULL CHECK (bpm BETWEEN 40 AND 200),
    musical_key TEXT,
    chord_timeline JSONB NOT NULL DEFAULT '[]'::jsonb,
    audio_fingerprint CHAR(64),
    similarity_matches JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

ALTER TABLE analysis_history ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS analysis_history_user_created_idx
    ON analysis_history (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS analysis_history_active_user_created_idx
    ON analysis_history (user_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS musical_tips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(100) NOT NULL,
    category VARCHAR(40) NOT NULL,
    content VARCHAR(1200) NOT NULL,
    exercise VARCHAR(500) NOT NULL,
    published BOOLEAN NOT NULL DEFAULT true,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT musical_tips_title_nonempty CHECK (length(trim(title)) >= 3),
    CONSTRAINT musical_tips_category_nonempty CHECK (length(trim(category)) >= 2),
    CONSTRAINT musical_tips_content_nonempty CHECK (length(trim(content)) >= 10),
    CONSTRAINT musical_tips_exercise_nonempty CHECK (length(trim(exercise)) >= 10)
);

ALTER TABLE musical_tips ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS musical_tips_public_idx
    ON musical_tips (category, title)
    WHERE published IS TRUE AND deleted_at IS NULL;

COMMIT;
