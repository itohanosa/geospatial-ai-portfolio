CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

CREATE TABLE IF NOT EXISTS system_metadata (
    metadata_key TEXT PRIMARY KEY,
    metadata_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO system_metadata (metadata_key, metadata_value)
VALUES
    ('platform_name', 'GeoRiskOS'),
    ('schema_version', 'step-1')
ON CONFLICT (metadata_key)
DO UPDATE SET
    metadata_value = EXCLUDED.metadata_value,
    updated_at = NOW();
