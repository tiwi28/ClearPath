CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS wards (
  ward_id int PRIMARY KEY,
  name text,
  geom geometry(MultiPolygon, 4326)
);

CREATE TABLE IF NOT EXISTS barriers (
  id bigserial,
  source text,          -- e.g. '311' or 'road_restriction'
  kind text,            -- e.g. 'sidewalk', 'closure', or 'curb'
  status text,
  opened_at timestamptz NOT NULL,
  closed_at timestamptz,
  ward_id int REFERENCES wards,
  geom geometry(Point, 4326),
  source_url text,
  raw jsonb
);
SELECT create_hypertable('barriers', 'opened_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS barriers_geom_idx ON barriers USING gist (geom);

-- Retain point locations while adding precise footprints for routing.
ALTER TABLE barriers ADD COLUMN IF NOT EXISTS verification text NOT NULL DEFAULT 'reported';
ALTER TABLE barriers ADD COLUMN IF NOT EXISTS blocks_route boolean NOT NULL DEFAULT false;
ALTER TABLE barriers ADD COLUMN IF NOT EXISTS avoidance_geom geometry(Geometry, 4326);
CREATE INDEX IF NOT EXISTS barriers_avoidance_geom_idx ON barriers USING gist (avoidance_geom);

-- Rider reports from trips: "blocked" or "clear" at a spot. Aggregated in app/reports.py.
CREATE TABLE IF NOT EXISTS rider_reports (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  device_id text NOT NULL,
  kind text NOT NULL,
  state text NOT NULL CHECK (state IN ('blocked', 'clear')),
  profile text,
  geom geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS rider_reports_geom_idx ON rider_reports USING gist (geom);
CREATE INDEX IF NOT EXISTS rider_reports_created_idx ON rider_reports (created_at);
