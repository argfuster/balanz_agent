-- Tabla para cachear cookies de sesión de Balanz
-- Ejecutar en Supabase SQL Editor

CREATE TABLE IF NOT EXISTS balanz_sessions (
    id          BIGSERIAL PRIMARY KEY,
    cookies     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice para que la query ORDER BY created_at DESC sea rápida
CREATE INDEX IF NOT EXISTS idx_balanz_sessions_created_at
    ON balanz_sessions (created_at DESC);

-- Limpiar sesiones viejas automáticamente (opcional)
-- Mantener solo las últimas 10
CREATE OR REPLACE FUNCTION cleanup_balanz_sessions()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM balanz_sessions
    WHERE id NOT IN (
        SELECT id FROM balanz_sessions
        ORDER BY created_at DESC
        LIMIT 10
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cleanup_sessions
AFTER INSERT ON balanz_sessions
FOR EACH ROW EXECUTE FUNCTION cleanup_balanz_sessions();
