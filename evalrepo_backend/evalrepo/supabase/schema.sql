-- ─────────────────────────────────────────────────────────────────────────────
-- EvalRepo — Schema SQL para Supabase
-- Ejecutar en: Dashboard Supabase → SQL Editor → New Query → Run
-- ─────────────────────────────────────────────────────────────────────────────

-- Tabla principal de evaluaciones
CREATE TABLE IF NOT EXISTS evaluations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status           TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'running', 'done', 'error')),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    total_repos      INTEGER NOT NULL DEFAULT 0,
    processed_repos  INTEGER NOT NULL DEFAULT 0,
    errors           JSONB NOT NULL DEFAULT '[]',
    criteria         JSONB NOT NULL DEFAULT '{}',
    consolidated_report TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Resultados por repositorio (uno por fila)
CREATE TABLE IF NOT EXISTS repo_results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id    UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    url              TEXT NOT NULL,
    owner            TEXT NOT NULL,
    repo_name        TEXT NOT NULL,
    student          TEXT NOT NULL,
    global_score     NUMERIC(5,2) NOT NULL DEFAULT 0,
    alerts           JSONB NOT NULL DEFAULT '[]',
    pattern_label    TEXT NOT NULL DEFAULT '',
    structural_result  JSONB,
    versioning_result  JSONB,
    temporal_result    JSONB,
    content_result     JSONB,
    report_html      TEXT,
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_repo_results_evaluation_id
    ON repo_results(evaluation_id);

CREATE INDEX IF NOT EXISTS idx_repo_results_student
    ON repo_results(evaluation_id, student, repo_name);

CREATE INDEX IF NOT EXISTS idx_evaluations_status
    ON evaluations(status, created_at DESC);

-- Row Level Security — el backend usa service_role (bypassa RLS)
ALTER TABLE evaluations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE repo_results ENABLE ROW LEVEL SECURITY;

-- Política permisiva para service_role (clave usada por el backend)
CREATE POLICY "service_role_all_evaluations"
    ON evaluations FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all_repo_results"
    ON repo_results FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─────────────────────────────────────────────────────────────────────────────
-- Migración: ajuste manual del puntaje desde la interfaz (PATCH /evaluate/.../score)
-- Ejecutar una sola vez en Dashboard Supabase → SQL Editor. Es idempotente
-- (IF NOT EXISTS), así que no pasa nada si la corres más de una vez.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE repo_results ADD COLUMN IF NOT EXISTS original_score NUMERIC(5,2);
ALTER TABLE repo_results ADD COLUMN IF NOT EXISTS score_overridden BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE repo_results ADD COLUMN IF NOT EXISTS override_note TEXT;
