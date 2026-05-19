unit WfEngine.Integration.Tests;

{
  Integration test skeleton for WfEngine.
  Configure TEST_DB_CONNECTION in environment or edit ConnectionString below.
  Requires: UniDAC, SQL Server with MethylPipeline wf schema deployed.
}

interface

// DUnitX-style manual runner hooks (host project can wire these procedures).

procedure RunAllIntegrationTests;

implementation

uses
  System.SysUtils,
  Uni,
  WfEngine.Scheduler,
  WfEngine.ServiceLoop,
  WfEngine.Types,
  WfEngine.WorkerApiAdapter;

function TestConnectionString: string;
begin
  Result := GetEnvironmentVariable('METHYLPIPELINE_DB');
  if Result = '' then
    Result := 'Provider Name=SQL Server;Data Source=localhost;Initial Catalog=MethylPipeline;Integrated Security=True';
end;

procedure AssertTrue(const ACondition: Boolean; const AMessage: string);
begin
  if not ACondition then
    raise Exception.Create('ASSERT FAILED: ' + AMessage);
end;

procedure TestJsonResolverIterationPlaceholder;
var
  Svc: TWorkflowEngineHostedService;
  Cfg: TWorkflowEngineServiceConfig;
  VersionId, InstanceId: Int64;
  Conn: TUniConnection;
  Q: TUniQuery;
begin
  Cfg.ConnectionString := TestConnectionString;
  Cfg.UseEngineSubmitPath := True;
  Cfg.PollIntervalMs := 500;
  Cfg.MaxInstancesPerTick := 10;
  Svc := TWorkflowEngineHostedService.Create(Cfg);
  Conn := TUniConnection.Create(nil);
  try
    Conn.ConnectString := Cfg.ConnectionString;
    Conn.Connect;
    Q := TUniQuery.Create(nil);
    try
      Q.Connection := Conn;
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
    Svc.RunOnce;
    AssertTrue(TWorkflowEngine(Svc.Engine).Repository.CountReadyTasks(InstanceId) > 0,
      'Scheduler should leave READY tasks after StartInstance.');
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
  Token: string;
  Claim: TWorkerTaskClaimResult;
  Ack: TSubmitResultAck;
  Conn: TUniConnection;
  Q: TUniQuery;
  VersionId, InstanceId: Int64;
begin
  Cfg.ConnectionString := TestConnectionString;
  Cfg.UseEngineSubmitPath := True;
  Svc := TWorkflowEngineHostedService.Create(Cfg);
  Conn := TUniConnection.Create(nil);
  try
    Conn.ConnectString := Cfg.ConnectionString;
    Conn.Connect;
    Q := TUniQuery.Create(nil);
    try
      Q.Connection := Conn;
      Q.SQL.Text := 'SELECT TOP 1 id FROM wf.worker WHERE status = ''REGISTERED'' ORDER BY id';
      Q.Open;
      AssertTrue(not Q.Eof, 'At least one registered worker required.');
      WorkerId := Q.Fields[0].AsLargeInt;
      Q.Close;
      Q.SQL.Text := Format(
        'SELECT TOP 1 token_prefix FROM wf.worker_token WHERE worker_id = %d AND status = ''ACTIVE''',
        [WorkerId]);
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
  TestJsonResolverIterationPlaceholder;
  // TestWorkerClaimSubmitLifecycle; // enable when worker token fixture is configured
end;

end.
