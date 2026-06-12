unit WfEngine.Integration.Tests;

{
  Integration test skeleton for the Delphi REST gateway.
  Configure METHYLPIPELINE_DB in the environment.
  Requires: UniDAC, wf schema deployed (wf_sql_runtime_parity.sql or equivalent).
}

interface

procedure RunAllIntegrationTests;

implementation

uses
  System.SysUtils,
  Uni,
  WfEngine.Connection,
  WfEngine.ServiceLoop,
  WfEngine.Types;

function TestConnectionConfig: TConnectionConfig;
begin
  Result := ResolveConnectionConfig;
  if Result.ConnectionString = '' then
  begin
    Result.Backend := dbMssql;
    Result.ConnectionString :=
      'Provider Name=SQL Server;Data Source=localhost;Initial Catalog=MethylPipeline;Integrated Security=True';
    Result.SchemaName := ResolveSchemaName;
    Result.UseManagedIdentity := False;
  end;
end;

procedure AssertTrue(const ACondition: Boolean; const AMessage: string);
begin
  if not ACondition then
    raise Exception.Create('ASSERT FAILED: ' + AMessage);
end;

procedure TestSqlStartInstanceCreatesReadyTasks;
var
  Svc: TWorkflowEngineHostedService;
  Cfg: TWorkflowEngineServiceConfig;
  VersionId, InstanceId: Int64;
  ReadyCount: Integer;
  Conn: TUniConnection;
  Q: TUniQuery;
  ConnCfg: TConnectionConfig;
begin
  ConnCfg := TestConnectionConfig;
  Cfg.Connection := ConnCfg;
  Svc := TWorkflowEngineHostedService.Create(Cfg);
  Conn := TUniConnection.Create(nil);
  try
    ConnectUniDatabase(Conn, ConnCfg);
    Q := TUniQuery.Create(nil);
    try
      Q.Connection := Conn;
      if GetDatabaseBackend = dbPostgres then
        Q.SQL.Text :=
          'SELECT wv.id FROM wf.workflow_version wv ' +
          'INNER JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id ' +
          'WHERE wd.name = ''DemoFlow'' ORDER BY wv.id DESC LIMIT 1'
      else
        Q.SQL.Text :=
          'SELECT TOP 1 wv.id FROM wf.workflow_version wv ' +
          'INNER JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id ' +
          'WHERE wd.name = ''DemoFlow'' ORDER BY wv.id DESC';
      Q.Open;
      AssertTrue(not Q.Eof, 'DemoFlow workflow version must exist (run seed).');
      VersionId := Q.Fields[0].AsLargeInt;
    finally
      Q.Free;
    end;

    InstanceId := Svc.CreateAndStartInstance(VersionId, '{}');
    AssertTrue(InstanceId > 0, 'Instance should be created.');

    Q := TUniQuery.Create(nil);
    try
      Q.Connection := Conn;
      Q.SQL.Text := Format(
        'SELECT COUNT(*) AS c FROM %snode_execution WHERE workflow_instance_id = :wi AND status = ''READY''',
        [ConnCfg.SchemaDot]);
      Q.ParamByName('wi').AsLargeInt := InstanceId;
      Q.Open;
      ReadyCount := Q.FieldByName('c').AsInteger;
    finally
      Q.Free;
    end;
    AssertTrue(ReadyCount > 0,
      'sp_start_workflow_instance should leave READY tasks after activation.');
  finally
    Conn.Free;
    Svc.Free;
  end;
end;

procedure TestWorkerClaimSubmitLifecycle;
var
  Cfg: TWorkflowEngineServiceConfig;
  Svc: TWorkflowEngineHostedService;
  WorkerId: Int64;
  Conn: TUniConnection;
  Q: TUniQuery;
  ConnCfg: TConnectionConfig;
begin
  ConnCfg := TestConnectionConfig;
  Cfg.Connection := ConnCfg;
  Svc := TWorkflowEngineHostedService.Create(Cfg);
  Conn := TUniConnection.Create(nil);
  try
    ConnectUniDatabase(Conn, ConnCfg);
    Q := TUniQuery.Create(nil);
    try
      Q.Connection := Conn;
      if GetDatabaseBackend = dbPostgres then
        Q.SQL.Text := 'SELECT id FROM wf.worker WHERE status = ''REGISTERED'' ORDER BY id LIMIT 1'
      else
        Q.SQL.Text := 'SELECT TOP 1 id FROM wf.worker WHERE status = ''REGISTERED'' ORDER BY id';
      Q.Open;
      AssertTrue(not Q.Eof, 'At least one registered worker required.');
      WorkerId := Q.Fields[0].AsLargeInt;
      Q.Close;
      Q.SQL.Text := Format(
        'SELECT token_prefix FROM wf.worker_token WHERE worker_id = %d AND status = ''ACTIVE''',
        [WorkerId]);
      if GetDatabaseBackend = dbPostgres then
        Q.SQL.Text := Q.SQL.Text + ' LIMIT 1'
      else
        Q.SQL.Text := 'SELECT TOP 1 token_prefix FROM wf.worker_token WHERE worker_id = ' +
          IntToStr(WorkerId) + ' AND status = ''ACTIVE''';
      Q.Open;
      AssertTrue(False, 'Configure a known worker token for automated claim/submit test.');
    finally
      Q.Free;
    end;
  finally
    Conn.Free;
    Svc.Free;
  end;
end;

procedure RunAllIntegrationTests;
begin
  TestSqlStartInstanceCreatesReadyTasks;
  // TestWorkerClaimSubmitLifecycle; // enable when worker token fixture is configured
end;

end.
