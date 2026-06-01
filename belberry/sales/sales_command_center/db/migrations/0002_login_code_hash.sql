-- login_codes.code now stores SHA-256 OTP hash, never plaintext.
ALTER TABLE login_codes ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
