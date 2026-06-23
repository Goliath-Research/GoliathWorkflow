/*
  MethylPipeline wf schema - PostgreSQL (core definition + runtime tables).
  Deploy first. Requires PostgreSQL 15+ (17+ recommended; PG 18+ on Azure).
  Uses pg_catalog sha256(bytea) — no pgcrypto extension required on Azure Flexible Server.
*/

CREATE SCHEMA IF NOT EXISTS wf;

CREATE OR REPLACE FUNCTION wf.wf_sha256_text(p_text text)
RETURNS bytea
LANGUAGE sql
IMMUTABLE PARALLEL SAFE
AS $$
  SELECT sha256(convert_to(coalesce(p_text, ''), 'UTF8'));
$$;

-- Definition layer
CREATE TABLE IF NOT EXISTS wf.workflow_def (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  description text NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS wf.workflow_version (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_def_id bigint NOT NULL REFERENCES wf.workflow_def(id),
  version_major int NOT NULL DEFAULT 1,
  version_minor int NOT NULL DEFAULT 0,
  is_active boolean NOT NULL DEFAULT true,
  root_node_id bigint NULL,
  UNIQUE (workflow_def_id, version_major, version_minor)
);

CREATE TABLE IF NOT EXISTS wf.workflow_action (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  action_name text NOT NULL UNIQUE,
  capability text NULL,
  payload_schema_ref text NULL
);

CREATE TABLE IF NOT EXISTS wf.workflow_node (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_version_id bigint NOT NULL REFERENCES wf.workflow_version(id) ON DELETE CASCADE,
  node_type varchar(32) NOT NULL,
  node_key text NOT NULL,
  workflow_action_id bigint NULL REFERENCES wf.workflow_action(id),
  repeat_count int NULL,
  condition_ref_node_key text NULL,
  switch_ref_node_key text NULL,
  condition_var text NULL,
  switch_var text NULL,
  foreach_collection_var text NULL,
  foreach_item_var text NULL,
  foreach_index_var text NULL,
  foreach_parallel boolean NULL,
  UNIQUE (workflow_version_id, node_key),
  CHECK (node_type IN ('ACTION','SEQUENCE','PARALLEL','IF','SWITCH','REPEAT','WHILE','FOREACH'))
);

ALTER TABLE wf.workflow_version
  ADD CONSTRAINT fk_wfv_root FOREIGN KEY (root_node_id) REFERENCES wf.workflow_node(id);

CREATE INDEX IF NOT EXISTS ix_workflow_node_version ON wf.workflow_node(workflow_version_id);

CREATE TABLE IF NOT EXISTS wf.workflow_edge (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  parent_node_id bigint NOT NULL REFERENCES wf.workflow_node(id),
  child_node_id bigint NOT NULL REFERENCES wf.workflow_node(id),
  child_order int NOT NULL DEFAULT 0,
  branch_kind varchar(32) NULL,
  condition_expr text NULL,
  switch_case_value int NULL,
  is_default boolean NOT NULL DEFAULT false,
  CHECK (parent_node_id <> child_node_id),
  CHECK (branch_kind IS NULL OR branch_kind IN ('SEQUENCE','PARALLEL','THEN','ELSE','CASE','DEFAULT','BODY'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_we_parent_child_order ON wf.workflow_edge(parent_node_id, child_order);
CREATE INDEX IF NOT EXISTS ix_we_parent ON wf.workflow_edge(parent_node_id);
CREATE INDEX IF NOT EXISTS ix_we_child ON wf.workflow_edge(child_node_id);

CREATE TABLE IF NOT EXISTS wf.workflow_input_template (
  workflow_node_id bigint PRIMARY KEY REFERENCES wf.workflow_node(id) ON DELETE CASCADE,
  template_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS wf.workflow_input_binding (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_node_id bigint NOT NULL REFERENCES wf.workflow_node(id) ON DELETE CASCADE,
  target_json_path text NOT NULL,
  source_expr text NOT NULL,
  is_required boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS ix_wib_node ON wf.workflow_input_binding(workflow_node_id);

CREATE TABLE IF NOT EXISTS wf.variable_output_binding (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_node_id bigint NOT NULL REFERENCES wf.workflow_node(id) ON DELETE CASCADE,
  var_name text NOT NULL,
  source_kind varchar(32) NOT NULL,
  source_json_path text NULL,
  UNIQUE (workflow_node_id, var_name),
  CHECK (source_kind IN ('output_path','result_code'))
);

CREATE TABLE IF NOT EXISTS wf.node_scope_default (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_node_id bigint NOT NULL REFERENCES wf.workflow_node(id) ON DELETE CASCADE,
  var_name text NOT NULL,
  default_expr text NOT NULL,
  UNIQUE (workflow_node_id, var_name)
);

-- Runtime layer
CREATE TABLE IF NOT EXISTS wf.workflow_instance (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_version_id bigint NOT NULL REFERENCES wf.workflow_version(id),
  status varchar(32) NOT NULL DEFAULT 'CREATED',
  context_json jsonb NULL,
  started_at_utc timestamptz NULL,
  completed_at_utc timestamptz NULL,
  CHECK (status IN ('CREATED','RUNNING','COMPLETED','FAILED','CANCELLED'))
);

CREATE INDEX IF NOT EXISTS ix_wi_version_status ON wf.workflow_instance(workflow_version_id, status);

CREATE TABLE IF NOT EXISTS wf.node_execution (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_instance_id bigint NOT NULL REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
  workflow_node_id bigint NOT NULL REFERENCES wf.workflow_node(id),
  status varchar(32) NOT NULL DEFAULT 'PENDING',
  attempt_no int NOT NULL DEFAULT 1,
  parent_node_execution_id bigint NULL REFERENCES wf.node_execution(id),
  iteration_no int NOT NULL DEFAULT 0,
  input_json jsonb NULL,
  output_json jsonb NULL,
  result_code int NULL,
  engine_error_code int NULL,
  engine_error_message text NULL,
  started_at_utc timestamptz NULL,
  ended_at_utc timestamptz NULL,
  available_at_utc timestamptz NULL,
  CHECK (status IN ('PENDING','READY','RUNNING','SUCCEEDED','FAILED','SKIPPED','CANCELLED'))
);

CREATE INDEX IF NOT EXISTS ix_ne_instance_status_avail ON wf.node_execution(workflow_instance_id, status, available_at_utc);
CREATE INDEX IF NOT EXISTS ix_ne_instance_node ON wf.node_execution(workflow_instance_id, workflow_node_id, status);

CREATE TABLE IF NOT EXISTS wf.execution_context (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  node_execution_id bigint NOT NULL REFERENCES wf.node_execution(id) ON DELETE CASCADE,
  context_key text NOT NULL,
  context_value_json jsonb NULL,
  UNIQUE (node_execution_id, context_key)
);

CREATE TABLE IF NOT EXISTS wf.loop_state (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_instance_id bigint NOT NULL REFERENCES wf.workflow_instance(id),
  control_node_id bigint NOT NULL REFERENCES wf.workflow_node(id),
  scope_node_execution_id bigint NOT NULL REFERENCES wf.node_execution(id),
  current_iteration int NOT NULL DEFAULT 0,
  repeat_target_count int NULL,
  UNIQUE (scope_node_execution_id)
);

CREATE TABLE IF NOT EXISTS wf.instance_cursor (
  workflow_instance_id bigint PRIMARY KEY REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
  last_polled_at_utc timestamptz NULL,
  notes text NULL
);

CREATE TABLE IF NOT EXISTS wf.scope_variable (
  workflow_instance_id bigint NOT NULL REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
  scope_node_execution_id bigint NOT NULL,
  var_name text NOT NULL,
  value_json jsonb NOT NULL,
  updated_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  PRIMARY KEY (workflow_instance_id, scope_node_execution_id, var_name)
);

CREATE INDEX IF NOT EXISTS ix_sv_instance_scope ON wf.scope_variable(workflow_instance_id, scope_node_execution_id);

-- Worker registry
CREATE TABLE IF NOT EXISTS wf.cluster (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cluster_key text NOT NULL UNIQUE,
  name text NOT NULL,
  provider text NULL,
  shared_storage_uri text NULL,
  worker_mount_path text NOT NULL DEFAULT '/work',
  status varchar(32) NOT NULL DEFAULT 'ACTIVE',
  allowed_source_cidrs jsonb NULL,
  entra_client_id text NULL,
  arc_resource_id text NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CHECK (status IN ('ACTIVE','DISABLED'))
);

CREATE TABLE IF NOT EXISTS wf.platform_sample_storage (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  storage_key text NOT NULL UNIQUE,
  provider_type varchar(32) NOT NULL DEFAULT 's3',
  bucket text NOT NULL,
  region text NULL,
  endpoint_url text NOT NULL,
  access_key_id text NOT NULL,
  secret_access_key text NOT NULL,
  base_prefix text NOT NULL DEFAULT 'samples/',
  status varchar(32) NOT NULL DEFAULT 'ACTIVE',
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CHECK (status IN ('ACTIVE','DISABLED'))
);

CREATE TABLE IF NOT EXISTS wf.worker (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cluster_id bigint NOT NULL REFERENCES wf.cluster(id),
  external_worker_key text NULL UNIQUE,
  display_name text NULL,
  hostname text NULL,
  capabilities jsonb NULL,
  status varchar(32) NOT NULL DEFAULT 'REGISTERED',
  last_seen_at_utc timestamptz NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CHECK (status IN ('REGISTERED','DISABLED'))
);

CREATE TABLE IF NOT EXISTS wf.worker_token (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  worker_id bigint NOT NULL REFERENCES wf.worker(id) ON DELETE CASCADE,
  token_hash bytea NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'ACTIVE',
  expires_at_utc timestamptz NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CHECK (status IN ('ACTIVE','REVOKED'))
);

CREATE TABLE IF NOT EXISTS wf.task_lease (
  node_execution_id bigint PRIMARY KEY REFERENCES wf.node_execution(id) ON DELETE CASCADE,
  worker_id bigint NOT NULL REFERENCES wf.worker(id),
  lease_expires_at_utc timestamptz NOT NULL,
  heartbeat_at_utc timestamptz NULL
);

CREATE INDEX IF NOT EXISTS ix_tl_worker_expiry ON wf.task_lease(worker_id, lease_expires_at_utc);

-- Generic instance extension (optional domain audit metadata)
CREATE TABLE IF NOT EXISTS wf.instance_extension (
  workflow_instance_id bigint NOT NULL REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
  extension_key text NOT NULL,
  data_json jsonb NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  PRIMARY KEY (workflow_instance_id, extension_key)
);

CREATE INDEX IF NOT EXISTS ix_ie_instance ON wf.instance_extension(workflow_instance_id);
