CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS wards (
  ward_id int PRIMARY KEY,
  name text,
  geom geometry(MultiPolygon, 4326)
);

CREATE TABLE IF NOT EXISTS barriers (
  id bigserial,
  source text,          -- '311' | 'road_restriction' | 'elevator' | 'audit'
  kind text,            -- 'sidewalk' | 'closure' | 'elevator_out' | 'curb'
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

CREATE TABLE IF NOT EXISTS stations (
  id text PRIMARY KEY,
  name text,
  ward_id int,
  has_elevator bool,
  elevator_status text,
  geom geometry(Point, 4326)
);
