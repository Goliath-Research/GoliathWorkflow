program WfEngineSrv;

{$APPTYPE CONSOLE}
{$STRONGLINKTYPES ON}

uses
  System.SysUtils,
  WfEngine.ServiceLoop in 'src\WfEngine.ServiceLoop.pas',
  WfEngine.Types in 'src\WfEngine.Types.pas',
  WfEngine.ControlFlow in 'src\WfEngine.ControlFlow.pas',
  WfEngine.Exceptions in 'src\WfEngine.Exceptions.pas',
  WfEngine.Interfaces in 'src\WfEngine.Interfaces.pas',
  WfEngine.JsonResolver in 'src\WfEngine.JsonResolver.pas',
  WfEngine in 'src\WfEngine.pas',
  WfEngine.Repository in 'src\WfEngine.Repository.pas',
  WfEngine.Scheduler in 'src\WfEngine.Scheduler.pas',
  WfEngine.Scope in 'src\WfEngine.Scope.pas',
  WfEngine.WorkerApiAdapter in 'src\WfEngine.WorkerApiAdapter.pas';

function GetArgValue(const Args: TArray<string>; const Name: string; const Default: string): string;
var
  I: Integer;
  Prefix: string;
begin
  Prefix := LowerCase(Name) + '=';
  for I := 0 to High(Args) do
    if LowerCase(Args[I]).StartsWith(Prefix) then
      Exit(Copy(Args[I], Length(Prefix) + 1, MaxInt));
  Result := Default;
end;

procedure PrintUsage;
begin
  Writeln('WfEngineSrv - MethylPipeline workflow engine host');
  Writeln;
  Writeln('Usage:');
  Writeln('  WfEngineSrv /run [pollms=1000] [maxinstances=50]');
  Writeln('  WfEngineSrv /startinstance version=<id> [context={}]');
  Writeln;
  Writeln('Environment:');
  Writeln('  METHYLPIPELINE_DB  UniDAC connection string (required)');
end;

var
  Cfg: TWorkflowEngineServiceConfig;
  Svc: TWorkflowEngineHostedService;
  Args: TArray<string>;
  Mode, Conn, Ctx: string;
  VersionId, InstanceId: Int64;
  I: Integer;
begin
  try
    SetLength(Args, ParamCount);
    for I := 1 to ParamCount do
      Args[I - 1] := ParamStr(I);

    if (Length(Args) = 0) or SameText(Args[0], '/?') or SameText(Args[0], '-h') or SameText(Args[0], '/help') then
    begin
      PrintUsage;
      Exit;
    end;

    Conn := GetEnvironmentVariable('METHYLPIPELINE_DB');
    if Conn = '' then
      raise Exception.Create('Set environment variable METHYLPIPELINE_DB to a UniDAC connection string.');

    Cfg.ConnectionString := Conn;
    Cfg.UseEngineSubmitPath := True;
    Cfg.PollIntervalMs := StrToIntDef(GetArgValue(Args, 'pollms', '1000'), 1000);
    Cfg.MaxInstancesPerTick := StrToIntDef(GetArgValue(Args, 'maxinstances', '50'), 50);

    Mode := LowerCase(Args[0]);
    Svc := TWorkflowEngineHostedService.Create(Cfg);
    try
      if Mode = '/run' then
      begin
        Writeln('Workflow engine running. Press Ctrl+C to stop.');
        Svc.RunUntilStopped;
      end
      else if Mode = '/startinstance' then
      begin
        VersionId := StrToInt64Def(GetArgValue(Args, 'version', '0'), 0);
        if VersionId <= 0 then
          raise Exception.Create('version=<workflow_version_id> is required.');
        Ctx := GetArgValue(Args, 'context', '{}');
        InstanceId := Svc.CreateAndStartInstance(VersionId, Ctx);
        Writeln(Format('Started workflow instance %d (version %d).', [InstanceId, VersionId]));
      end
      else
        PrintUsage;
    finally
      Svc.Free;
    end;
  except
    on E: Exception do
    begin
      Writeln(E.ClassName, ': ', E.Message);
      ExitCode := 1;
    end;
  end;
end.
