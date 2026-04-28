/*
  Workflow Engine - Runtime Layer (SQL Server)
  Instances, node executions, execution context, leases, loop state.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.execution_context', N'U') IS NOT NULL DROP TABLE dbo.execution_context;
IF OBJECT_ID(N'dbo.task_lease', N'U') IS NOT NULL DROP TABLE dbo.task_lease;
IF OBJECT_ID(N'dbo.loop_state', N'U') IS NOT NULL DROP TABLE dbo.loop_state;
IF OBJECT_ID(N'dbo.instance_cursor', N'U') IS NOT NULL DROP TABLE dbo.instance_cursor;
IF OBJECT_ID(N'dbo.node_execution', N'U') IS NOT NULL DROP TABLE dbo.node_execution;
IF OBJECT_ID(N'dbo.workflow_instance', N'U') IS NOT NULL DROP TABLE dbo.workflow_instance;
GO

CREATE TABLE dbo.workflow_instance (
    id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    workflow_version_id BIGINT NOT NULL,
    status              VARCHAR(32) NOT NULL CONSTRAINT DF_wi_status DEFAULT (N'CREATED'),
    context_json        NVARCHAR(MAX) NULL,
    started_at_utc      DATETIME2(7) NULL,
    completed_at_utc    DATETIME2(7) NULL,
    CONSTRAINT FK_wi_version FOREIGN KEY (workflow_version_id) REFERENCES dbo.workflow_version(id),
    CONSTRAINT CK_wi_status CHECK (status IN (N'CREATED', N'RUNNING', N'COMPLETED', N'FAILED', N'CANCELLED'))
);
GO

CREATE INDEX IX_wi_version_status ON dbo.workflow_instance(workflow_version_id, status);
GO

CREATE TABLE dbo.node_execution (
    id                      BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    workflow_instance_id    BIGINT NOT NULL,
    workflow_node_id        BIGINT NOT NULL,
    status                  VARCHAR(32) NOT NULL CONSTRAINT DF_ne_status DEFAULT (N'PENDING'),
    attempt_no              INT NOT NULL CONSTRAINT DF_ne_attempt DEFAULT (1),
    parent_node_execution_id BIGINT NULL,
    iteration_no            INT NOT NULL CONSTRAINT DF_ne_iter DEFAULT (0),
    input_json              NVARCHAR(MAX) NULL,
    output_json             NVARCHAR(MAX) NULL,
    result_code             INT NULL,
    engine_error_code       INT NULL,
    engine_error_message    NVARCHAR(1024) NULL,
    started_at_utc          DATETIME2(7) NULL,
    ended_at_utc            DATETIME2(7) NULL,
    available_at_utc        DATETIME2(7) NULL,
    CONSTRAINT FK_ne_instance FOREIGN KEY (workflow_instance_id) REFERENCES dbo.workflow_instance(id) ON DELETE CASCADE,
    CONSTRAINT FK_ne_node FOREIGN KEY (workflow_node_id) REFERENCES dbo.workflow_node(id),
    CONSTRAINT FK_ne_parent_exec FOREIGN KEY (parent_node_execution_id) REFERENCES dbo.node_execution(id),
    CONSTRAINT CK_ne_status CHECK (status IN (
        N'PENDING', N'READY', N'RUNNING', N'SUCCEEDED', N'FAILED', N'SKIPPED', N'CANCELLED'
    ))
);
GO

CREATE INDEX IX_ne_instance_status_avail ON dbo.node_execution(workflow_instance_id, status, available_at_utc)
    INCLUDE (workflow_node_id);
CREATE INDEX IX_ne_instance_node ON dbo.node_execution(workflow_instance_id, workflow_node_id, status);
GO

CREATE TABLE dbo.execution_context (
    id                      BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    node_execution_id       BIGINT NOT NULL,
    context_key             NVARCHAR(256) NOT NULL,
    context_value_json      NVARCHAR(MAX) NULL,
    CONSTRAINT FK_ec_ne FOREIGN KEY (node_execution_id) REFERENCES dbo.node_execution(id) ON DELETE CASCADE,
    CONSTRAINT UQ_ec_ne_key UNIQUE (node_execution_id, context_key)
);
GO

CREATE INDEX IX_ec_ne ON dbo.execution_context(node_execution_id);
GO

CREATE TABLE dbo.task_lease (
    node_execution_id       BIGINT NOT NULL PRIMARY KEY,
    worker_id               NVARCHAR(128) NOT NULL,
    lease_expires_at_utc    DATETIME2(7) NOT NULL,
    heartbeat_at_utc        DATETIME2(7) NULL,
    CONSTRAINT FK_tl_ne FOREIGN KEY (node_execution_id) REFERENCES dbo.node_execution(id) ON DELETE CASCADE
);
GO

CREATE INDEX IX_tl_worker_expiry ON dbo.task_lease(worker_id, lease_expires_at_utc);
GO

CREATE TABLE dbo.loop_state (
    id                      BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    workflow_instance_id    BIGINT NOT NULL,
    control_node_id         BIGINT NOT NULL,
    scope_node_execution_id BIGINT NOT NULL,
    current_iteration       INT NOT NULL CONSTRAINT DF_ls_cur DEFAULT (0),
    repeat_target_count     INT NULL,
    CONSTRAINT FK_ls_instance FOREIGN KEY (workflow_instance_id) REFERENCES dbo.workflow_instance(id) ON DELETE CASCADE,
    CONSTRAINT FK_ls_control FOREIGN KEY (control_node_id) REFERENCES dbo.workflow_node(id),
    CONSTRAINT FK_ls_scope FOREIGN KEY (scope_node_execution_id) REFERENCES dbo.node_execution(id) ON DELETE CASCADE,
    CONSTRAINT UQ_ls_scope UNIQUE (scope_node_execution_id)
);
GO

CREATE INDEX IX_ls_instance ON dbo.loop_state(workflow_instance_id, control_node_id);
GO

CREATE TABLE dbo.instance_cursor (
    workflow_instance_id    BIGINT NOT NULL PRIMARY KEY,
    last_polled_at_utc      DATETIME2(7) NULL,
    notes                   NVARCHAR(512) NULL,
    CONSTRAINT FK_ic_instance FOREIGN KEY (workflow_instance_id) REFERENCES dbo.workflow_instance(id) ON DELETE CASCADE
);
GO
