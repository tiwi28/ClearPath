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
