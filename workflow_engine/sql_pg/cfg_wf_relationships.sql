-- cfg ↔ wf relationships (additive; safe to re-run).

ALTER TABLE cfg.domain_program
  ADD COLUMN IF NOT EXISTS workflow_def_id bigint NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_cfg_dp_workflow_def'
  ) THEN
    ALTER TABLE cfg.domain_program
      ADD CONSTRAINT fk_cfg_dp_workflow_def
      FOREIGN KEY (workflow_def_id) REFERENCES wf.workflow_def(id);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_cfg_dp_compiled_version'
  ) THEN
    ALTER TABLE cfg.domain_program
      ADD CONSTRAINT fk_cfg_dp_compiled_version
      FOREIGN KEY (compiled_workflow_version_id) REFERENCES wf.workflow_version(id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_cfg_dp_compiled_version
  ON cfg.domain_program (compiled_workflow_version_id);
CREATE INDEX IF NOT EXISTS ix_cfg_dp_workflow_def
  ON cfg.domain_program (workflow_def_id);

ALTER TABLE cfg.action_definition
  ADD COLUMN IF NOT EXISTS workflow_action_id bigint NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_cfg_ad_workflow_action'
  ) THEN
    ALTER TABLE cfg.action_definition
      ADD CONSTRAINT fk_cfg_ad_workflow_action
      FOREIGN KEY (workflow_action_id) REFERENCES wf.workflow_action(id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_cfg_ad_workflow_action
  ON cfg.action_definition (workflow_action_id);

ALTER TABLE cfg.storage_endpoint
  ADD COLUMN IF NOT EXISTS credential_id bigint NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_cfg_se_credential'
  ) THEN
    ALTER TABLE cfg.storage_endpoint
      ADD CONSTRAINT fk_cfg_se_credential
      FOREIGN KEY (credential_id) REFERENCES cfg.credential(id);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS cfg.study_instance_link (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  study_row_id bigint NOT NULL REFERENCES cfg.study(id),
  workflow_instance_id bigint NOT NULL REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
  domain_program_id bigint NULL REFERENCES cfg.domain_program(id),
  pipeline_profile_id bigint NULL REFERENCES cfg.pipeline_profile(id),
  site_id bigint NULL REFERENCES cfg.site(id),
  storage_profile_id bigint NULL REFERENCES cfg.storage_profile(id),
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT uq_cfg_sil_instance UNIQUE (workflow_instance_id)
);

CREATE INDEX IF NOT EXISTS ix_cfg_sil_study ON cfg.study_instance_link (study_row_id);
CREATE INDEX IF NOT EXISTS ix_cfg_sil_program ON cfg.study_instance_link (domain_program_id);

CREATE TABLE IF NOT EXISTS cfg.program_publish (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  domain_program_id bigint NOT NULL REFERENCES cfg.domain_program(id),
  workflow_def_id bigint NOT NULL REFERENCES wf.workflow_def(id),
  workflow_version_id bigint NOT NULL REFERENCES wf.workflow_version(id),
  content_hash text NOT NULL,
  published_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT uq_cfg_ppub_program_version UNIQUE (domain_program_id, workflow_version_id)
);

CREATE INDEX IF NOT EXISTS ix_cfg_ppub_version ON cfg.program_publish (workflow_version_id);

CREATE OR REPLACE VIEW cfg.v_domain_program_wf AS
SELECT
  p.id AS domain_program_id,
  p.name AS program_name,
  p.version AS program_version,
  p.status,
  p.content_hash,
  p.workflow_def_id,
  d.name AS workflow_def_name,
  p.compiled_workflow_version_id,
  v.version_major,
  v.version_minor,
  v.is_active
FROM cfg.domain_program p
LEFT JOIN wf.workflow_def d ON d.id = p.workflow_def_id
LEFT JOIN wf.workflow_version v ON v.id = p.compiled_workflow_version_id;

CREATE OR REPLACE VIEW cfg.v_action_definition_wf AS
SELECT
  a.id AS action_definition_id,
  a.name AS action_name,
  a.version AS action_version,
  a.status,
  a.implementation_status,
  a.workflow_action_id,
  wa.action_name AS wf_action_name,
  wa.capability
FROM cfg.action_definition a
LEFT JOIN wf.workflow_action wa ON wa.id = a.workflow_action_id;

CREATE OR REPLACE VIEW cfg.v_study_instance AS
SELECT
  l.id AS link_id,
  l.study_row_id,
  s.name AS study_name,
  s.study_id,
  l.workflow_instance_id,
  i.status AS instance_status,
  i.workflow_version_id,
  l.domain_program_id,
  p.name AS program_name,
  l.pipeline_profile_id,
  pr.name AS profile_name,
  l.site_id,
  l.created_at_utc
FROM cfg.study_instance_link l
INNER JOIN cfg.study s ON s.id = l.study_row_id
INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
LEFT JOIN cfg.domain_program p ON p.id = l.domain_program_id
LEFT JOIN cfg.pipeline_profile pr ON pr.id = l.pipeline_profile_id;
