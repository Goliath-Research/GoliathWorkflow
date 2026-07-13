/*
  cfg ↔ wf relationships (additive; safe to re-run).
  Bridges configuration registry to the workflow engine without putting science
  config tables inside wf.
*/

/* --- domain_program → wf.workflow_def / wf.workflow_version --- */
IF COL_LENGTH(N'cfg.domain_program', N'workflow_def_id') IS NULL
BEGIN
    ALTER TABLE cfg.domain_program ADD workflow_def_id bigint NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_dp_workflow_def'
)
BEGIN
    ALTER TABLE cfg.domain_program
      ADD CONSTRAINT FK_cfg_dp_workflow_def
      FOREIGN KEY (workflow_def_id) REFERENCES wf.workflow_def (id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_dp_compiled_version'
)
BEGIN
    ALTER TABLE cfg.domain_program
      ADD CONSTRAINT FK_cfg_dp_compiled_version
      FOREIGN KEY (compiled_workflow_version_id) REFERENCES wf.workflow_version (id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_dp_compiled_version' AND object_id = OBJECT_ID(N'cfg.domain_program')
)
BEGIN
    CREATE INDEX IX_cfg_dp_compiled_version ON cfg.domain_program (compiled_workflow_version_id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_dp_workflow_def' AND object_id = OBJECT_ID(N'cfg.domain_program')
)
BEGIN
    CREATE INDEX IX_cfg_dp_workflow_def ON cfg.domain_program (workflow_def_id);
END
GO

/* --- action_definition → wf.workflow_action --- */
IF COL_LENGTH(N'cfg.action_definition', N'workflow_action_id') IS NULL
BEGIN
    ALTER TABLE cfg.action_definition ADD workflow_action_id bigint NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_ad_workflow_action'
)
BEGIN
    ALTER TABLE cfg.action_definition
      ADD CONSTRAINT FK_cfg_ad_workflow_action
      FOREIGN KEY (workflow_action_id) REFERENCES wf.workflow_action (id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_ad_workflow_action' AND object_id = OBJECT_ID(N'cfg.action_definition')
)
BEGIN
    CREATE INDEX IX_cfg_ad_workflow_action ON cfg.action_definition (workflow_action_id);
END
GO

/* --- storage_endpoint → cfg.credential (internal) --- */
IF COL_LENGTH(N'cfg.storage_endpoint', N'credential_id') IS NULL
BEGIN
    ALTER TABLE cfg.storage_endpoint ADD credential_id bigint NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_se_credential'
)
BEGIN
    ALTER TABLE cfg.storage_endpoint
      ADD CONSTRAINT FK_cfg_se_credential
      FOREIGN KEY (credential_id) REFERENCES cfg.credential (id);
END
GO

/* --- study run link: cfg.study (+ profile/program/site) ↔ wf.workflow_instance --- */
IF OBJECT_ID(N'cfg.study_instance_link', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.study_instance_link (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        study_row_id bigint NOT NULL,
        workflow_instance_id bigint NOT NULL,
        domain_program_id bigint NULL,
        pipeline_profile_id bigint NULL,
        site_id bigint NULL,
        storage_profile_id bigint NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_sil_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT uq_cfg_sil_instance UNIQUE (workflow_instance_id),
        CONSTRAINT FK_cfg_sil_study FOREIGN KEY (study_row_id) REFERENCES cfg.study (id),
        CONSTRAINT FK_cfg_sil_instance FOREIGN KEY (workflow_instance_id) REFERENCES wf.workflow_instance (id) ON DELETE CASCADE,
        CONSTRAINT FK_cfg_sil_program FOREIGN KEY (domain_program_id) REFERENCES cfg.domain_program (id),
        CONSTRAINT FK_cfg_sil_profile FOREIGN KEY (pipeline_profile_id) REFERENCES cfg.pipeline_profile (id),
        CONSTRAINT FK_cfg_sil_site FOREIGN KEY (site_id) REFERENCES cfg.site (id),
        CONSTRAINT FK_cfg_sil_storage_profile FOREIGN KEY (storage_profile_id) REFERENCES cfg.storage_profile (id)
    );
    CREATE INDEX IX_cfg_sil_study ON cfg.study_instance_link (study_row_id);
    CREATE INDEX IX_cfg_sil_program ON cfg.study_instance_link (domain_program_id);
END
GO

/* --- publish audit: DomainProgram publish → concrete wf version --- */
IF OBJECT_ID(N'cfg.program_publish', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.program_publish (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        domain_program_id bigint NOT NULL,
        workflow_def_id bigint NOT NULL,
        workflow_version_id bigint NOT NULL,
        content_hash nvarchar(128) NOT NULL,
        published_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_ppub_at DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_cfg_ppub_program FOREIGN KEY (domain_program_id) REFERENCES cfg.domain_program (id),
        CONSTRAINT FK_cfg_ppub_def FOREIGN KEY (workflow_def_id) REFERENCES wf.workflow_def (id),
        CONSTRAINT FK_cfg_ppub_version FOREIGN KEY (workflow_version_id) REFERENCES wf.workflow_version (id),
        CONSTRAINT uq_cfg_ppub_program_version UNIQUE (domain_program_id, workflow_version_id)
    );
    CREATE INDEX IX_cfg_ppub_version ON cfg.program_publish (workflow_version_id);
END
GO

/* Convenience views */
CREATE OR ALTER VIEW cfg.v_domain_program_wf AS
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
GO

CREATE OR ALTER VIEW cfg.v_action_definition_wf AS
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
GO

CREATE OR ALTER VIEW cfg.v_study_instance AS
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
GO
