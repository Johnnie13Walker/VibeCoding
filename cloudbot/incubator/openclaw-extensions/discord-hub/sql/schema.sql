CREATE TABLE IF NOT EXISTS sync_registry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_record_id TEXT NOT NULL,
  discord_channel_id TEXT NOT NULL,
  discord_message_id TEXT,
  payload_hash TEXT NOT NULL,
  last_synced_at TEXT NOT NULL,
  UNIQUE(external_record_id, discord_channel_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_registry_last_synced_at
ON sync_registry(last_synced_at);
