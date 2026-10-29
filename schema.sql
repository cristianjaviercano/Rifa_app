-- SGRS: esquema PostgreSQL 16
-- gen_random_uuid() es nativo desde PostgreSQL 13: no requiere extensiones

CREATE TYPE user_role AS ENUM ('SUPERUSER','USER');
CREATE TYPE raffle_status AS ENUM ('DRAFT','OPEN','CLOSED','DRAWN','CANCELLED');
CREATE TYPE draw_method AS ENUM ('INTERNAL_CSPRNG','EXTERNAL_LOTTERY');
CREATE TYPE ticket_status AS ENUM ('DISPONIBLE','CONGELADO','PAGADO','GANADOR');
CREATE TYPE pay_platform AS ENUM ('NEQUI','DAVIPLATA','BREVE','PAYPAL','OTRO');
CREATE TYPE tx_status AS ENUM ('PENDING','APPROVED','REJECTED','EXPIRED');
CREATE TYPE prize_kind AS ENUM ('MAIN','SECO','CONSECUTIVE');

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone_e164 text NOT NULL UNIQUE,
  phone_verified_at timestamptz,
  name text NOT NULL,
  role user_role NOT NULL DEFAULT 'USER',
  notify_optout boolean NOT NULL DEFAULT false,
  room_code text UNIQUE,   -- código de la sala (portafolio) del organizador: S + 7 caracteres
  room_name text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raffles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid NOT NULL REFERENCES users(id),
  title text NOT NULL,
  terms_md text NOT NULL,
  total_numbers int NOT NULL CHECK (total_numbers > 0),
  numbers_per_ticket int NOT NULL CHECK (numbers_per_ticket > 0),
  ticket_price numeric(12,2) NOT NULL CHECK (ticket_price > 0),
  currency char(3) NOT NULL DEFAULT 'COP',
  sales_close_at timestamptz NOT NULL,
  draw_at timestamptz NOT NULL,
  draw_method draw_method NOT NULL,
  lottery_name text,
  hold_minutes int NOT NULL DEFAULT 120 CHECK (hold_minutes > 0),
  payment_accounts jsonb NOT NULL DEFAULT '{}',
  share_code text UNIQUE,  -- código corto para entrar a esta rifa: R + 7 caracteres
  visibility text NOT NULL DEFAULT 'PORTFOLIO' CHECK (visibility IN ('PORTFOLIO','LINK')),
  referrer_raffle_id uuid REFERENCES raffles(id),  -- rifa desde cuyo enlace nació esta (crecimiento viral)
  status raffle_status NOT NULL DEFAULT 'DRAFT',
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (sales_close_at < draw_at),
  CHECK (total_numbers % numbers_per_ticket = 0),
  CHECK (draw_method <> 'EXTERNAL_LOTTERY' OR lottery_name IS NOT NULL)
);

CREATE TABLE raffle_images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raffle_id uuid NOT NULL REFERENCES raffles(id) ON DELETE CASCADE,
  url text NOT NULL, sort int NOT NULL DEFAULT 0
);

CREATE TABLE prizes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raffle_id uuid NOT NULL REFERENCES raffles(id) ON DELETE CASCADE,
  kind prize_kind NOT NULL, rank int NOT NULL DEFAULT 1,
  description text NOT NULL, rule jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE tickets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raffle_id uuid NOT NULL REFERENCES raffles(id) ON DELETE CASCADE,
  serial int NOT NULL,
  status ticket_status NOT NULL DEFAULT 'DISPONIBLE',
  hold_expires_at timestamptz,
  owner_id uuid REFERENCES users(id),
  UNIQUE (raffle_id, serial),
  CHECK ((status = 'DISPONIBLE') = (owner_id IS NULL))
);
CREATE INDEX tickets_available_idx ON tickets (raffle_id) WHERE status = 'DISPONIBLE';

CREATE TABLE ticket_numbers (
  raffle_id uuid NOT NULL REFERENCES raffles(id) ON DELETE CASCADE,
  number int NOT NULL,
  ticket_id uuid NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  PRIMARY KEY (raffle_id, number)
);

-- Comprobantes de pago (el binario vive en el almacenamiento; aquí solo metadatos)
CREATE TABLE proofs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  uploader_id uuid NOT NULL REFERENCES users(id),
  sha256 text NOT NULL,
  mime text NOT NULL,
  size int NOT NULL,
  storage_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Almacenamiento de comprobantes en la propia base (SGRS_STORAGE=db): sin servicio extra, privado por diseño
CREATE TABLE proof_blobs (
  storage_key text PRIMARY KEY,
  data bytea NOT NULL
);

CREATE TABLE payment_transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raffle_id uuid NOT NULL REFERENCES raffles(id),
  buyer_id uuid NOT NULL REFERENCES users(id),
  platform pay_platform NOT NULL,
  external_ref text,
  proof_id uuid REFERENCES proofs(id),
  proof_sha256 text,
  amount_declared numeric(12,2) NOT NULL,
  status tx_status NOT NULL DEFAULT 'PENDING',
  expires_at timestamptz NOT NULL,
  reviewed_by uuid REFERENCES users(id),
  reviewed_at timestamptz,
  reject_reason text,
  idempotency_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (buyer_id, idempotency_key),
  CHECK (external_ref IS NOT NULL OR proof_id IS NOT NULL)
);
CREATE UNIQUE INDEX tx_ref_active_uq ON payment_transactions (raffle_id, platform, external_ref)
  WHERE status IN ('PENDING','APPROVED') AND external_ref IS NOT NULL;

CREATE TABLE transaction_tickets (
  transaction_id uuid NOT NULL REFERENCES payment_transactions(id) ON DELETE CASCADE,
  ticket_id uuid NOT NULL REFERENCES tickets(id),
  unit_price numeric(12,2) NOT NULL,
  PRIMARY KEY (transaction_id, ticket_id)
);

CREATE TABLE accounting_closures (
  raffle_id uuid PRIMARY KEY REFERENCES raffles(id),
  sold_count int NOT NULL, validated_amount numeric(14,2) NOT NULL,
  pending_amount numeric(14,2) NOT NULL, snapshot jsonb NOT NULL,
  hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE draws (
  raffle_id uuid PRIMARY KEY REFERENCES raffles(id),
  method draw_method NOT NULL, winning_number int NOT NULL,
  source_url text, executed_by uuid REFERENCES users(id),
  executed_at timestamptz NOT NULL DEFAULT now(),
  CHECK (method <> 'EXTERNAL_LOTTERY' OR source_url IS NOT NULL)
);

CREATE TABLE winners (
  raffle_id uuid NOT NULL REFERENCES draws(raffle_id),
  prize_id uuid NOT NULL REFERENCES prizes(id),
  ticket_id uuid NOT NULL REFERENCES tickets(id),
  PRIMARY KEY (raffle_id, prize_id)
);

-- Outbox transaccional de notificaciones
CREATE TABLE notifications (
  id bigserial PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id),
  raffle_id uuid REFERENCES raffles(id),
  type text NOT NULL, ref_id uuid, channel text NOT NULL DEFAULT 'WHATSAPP',
  payload jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'QUEUED',  -- QUEUED | SENT | FAILED | SKIPPED
  attempts int NOT NULL DEFAULT 0,
  scheduled_at timestamptz NOT NULL DEFAULT now(),
  provider_msg_id text, delivery_status text, last_error text, sent_at timestamptz,
  UNIQUE (user_id, type, ref_id)
);
CREATE INDEX notifications_queue_idx ON notifications (scheduled_at) WHERE status = 'QUEUED';
CREATE INDEX notifications_msg_idx ON notifications (provider_msg_id);

-- Bitácora append-only con hash encadenado
CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  actor_id uuid, action text NOT NULL, entity text NOT NULL, entity_id uuid,
  diff jsonb NOT NULL DEFAULT '{}', prev_hash text, hash text NOT NULL,
  ts timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION audit_immutable() RETURNS trigger LANGUAGE plpgsql AS
$$ BEGIN RAISE EXCEPTION 'audit_log es append-only'; END $$;
CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_immutable();

-- Login por OTP (el código nunca se guarda en claro)
CREATE TABLE otp_codes (
  id bigserial PRIMARY KEY,
  phone_e164 text NOT NULL,
  code_hash text NOT NULL,
  expires_at timestamptz NOT NULL,
  attempts int NOT NULL DEFAULT 0,
  consumed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX otp_phone_idx ON otp_codes (phone_e164, created_at DESC);


-- Salas a las que un usuario ha entrado (para volver a ellas); no concede acceso, solo recuerda
CREATE TABLE memberships (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, owner_id)
);
