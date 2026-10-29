-- Límites de tasa (contador por ventana) y consentimiento de términos
CREATE TABLE rate_limits (
  bucket text NOT NULL,
  key text NOT NULL,
  window_start timestamptz NOT NULL,
  hits int NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket, key, window_start)
);
CREATE INDEX rate_limits_old_idx ON rate_limits (window_start);

ALTER TABLE users ADD COLUMN terms_accepted_at timestamptz;
ALTER TABLE users ADD COLUMN terms_version text;
