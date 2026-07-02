program WfEngineSrv;

//{
//  FROZEN REFERENCE (2026-06): Delphi workflow REST gateway (DelphiMVCFramework).
//  Production gateway is Python methyl-gateway on Linux (see DELPHI_GATEWAY_STATUS.md).
//  No new routes or OpenAPI parity work is expected on this host.
//
//  MethylPipeline workflow REST gateway (DelphiMVCFramework, HTTP.sys backend).
//
//  Default mode: Windows service (MethylWfGateway). Supports the standard
//  VCL service switches (/install, /uninstall) and SCM start/pause/continue/stop.
//
//  Development modes:
//    WfEngineSrv /console [port=8080]
//    WfEngineSrv /startinstance version=<id> [context={}]
//}

{$APPTYPE CONSOLE}

uses
  Vcl.SvcMgr,
  System.SysUtils,
  WfEngine.Connection in 'src\WfEngine.Connection.pas',
  WfEngine.Types in 'src\WfEngine.Types.pas',
  WfEngine.Interfaces in 'src\WfEngine.Interfaces.pas',
  WfEngine.GatewayDb in 'src\WfEngine.GatewayDb.pas',
  WfEngine.WorkerApiAdapter in 'src\WfEngine.WorkerApiAdapter.pas',
  WfEngine.ServiceLoop in 'src\WfEngine.ServiceLoop.pas',
  WfEngine.GatewayDtos in 'src\WfEngine.GatewayDtos.pas',
  WfEngine.GatewayService in 'src\WfEngine.GatewayService.pas',
  WfEngine.GatewayHost in 'src\WfEngine.GatewayHost.pas',
  WfEngine.Mvc.WorkersController in 'src\WfEngine.Mvc.WorkersController.pas',
  WfEngine.Mvc.WorkflowsController in 'src\WfEngine.Mvc.WorkflowsController.pas',
  WfEngine.Mvc.ActionsController in 'src\WfEngine.Mvc.ActionsController.pas',
  WfEngine.Mvc.Server in 'src\WfEngine.Mvc.Server.pas',
  WfEngine.Mvc.Service in 'src\WfEngine.Mvc.Service.pas' {MethylWfGateway: TService};

function GetArgValue(const Name, Default: string): string;
var
  I: Integer;
  Prefix, Arg: string;
begin
  Prefix := LowerCase(Name) + '=';
  for I := 1 to ParamCount do
  begin
    Arg := ParamStr(I);
    if LowerCase(Arg).StartsWith(Prefix) then
      Exit(Copy(Arg, Length(Prefix) + 1, MaxInt));
  end;
  Result := Default;
end;

procedure PrintUsage;
begin
  Writeln('WfEngineSrv - MethylPipeline workflow REST gateway (Windows service, HTTP.sys)');
  Writeln;
  Writeln('Service management:');
  Writeln('  WfEngineSrv /install                      register service MethylWfGateway');
  Writeln('  WfEngineSrv /uninstall                    remove the service');
  Writeln('  sc start|pause|continue|stop MethylWfGateway');
  Writeln;
  Writeln('Development:');
  Writeln('  WfEngineSrv /console [port=8080]          run gateway in the foreground (localhost)');
  Writeln('  WfEngineSrv /startinstance version=<id> [context={}]');
  Writeln;
  Writeln('Environment:');
  Writeln('  METHYLPIPELINE_DB  UniDAC connection string (required)');
  Writeln('  BACKEND_DB         mssql | postgres (optional)');
  Writeln('  WF_GATEWAY_PORT    HTTP port (default 8080)');
  Writeln('  WF_GATEWAY_HOST    HTTP.sys host binding (service default ''+'', console ''localhost'')');
  Writeln('  WF_USE_MANAGED_IDENTITY  1 | true for Azure Entra ID via IMDS (production)');
end;

procedure RunConsole;
var
  Server: TWfGatewayServer;
  Port: Integer;
  Host: string;
begin
  Port := StrToIntDef(GetArgValue('port', ''), ResolveGatewayPort);
  // 'localhost' needs no HTTP.sys URL ACL; override with WF_GATEWAY_HOST.
  Host := ResolveGatewayHost('localhost');
  InitGatewayHost(ResolveGatewayConnectionConfig);
  Server := TWfGatewayServer.Create(Port, Host);
  try
    Server.Start;
    Writeln(Format('REST API listening on http://%s:%d/v1 (HTTP.sys)', [Host, Port]));
    Writeln('Press Ctrl+C to stop.');
    while True do
      Sleep(1000);
  finally
    Server.Free;
    ShutdownGatewayHost;
  end;
end;

procedure RunStartInstance;
var
  Cfg: TWorkflowEngineServiceConfig;
  Svc: TWorkflowEngineHostedService;
  VersionId, InstanceId: Int64;
  Ctx: string;
begin
  VersionId := StrToInt64Def(GetArgValue('version', '0'), 0);
  if VersionId <= 0 then
    raise Exception.Create('version=<workflow_version_id> is required.');
  Ctx := GetArgValue('context', '{}');
  Cfg.Connection := ResolveGatewayConnectionConfig;
  Svc := TWorkflowEngineHostedService.Create(Cfg);
  try
    InstanceId := Svc.CreateAndStartInstance(VersionId, Ctx);
    Writeln(Format('Started workflow instance %d (version %d).', [InstanceId, VersionId]));
  finally
    Svc.Free;
  end;
end;

begin
  try
    if FindCmdLineSwitch('?', True) or FindCmdLineSwitch('h', True) or FindCmdLineSwitch('help', True) then
    begin
      PrintUsage;
      Exit;
    end;

    if FindCmdLineSwitch('console', True) then
    begin
      RunConsole;
      Exit;
    end;

    if FindCmdLineSwitch('startinstance', True) then
    begin
      RunStartInstance;
      Exit;
    end;

    // Default: run under the Windows Service Control Manager
    // (also handles /install and /uninstall).
    if not Application.DelayInitialize or Application.Installing then
      Application.Initialize;
    Application.CreateForm(TMethylWfGatewayService, MethylWfGateway);
    Application.Run;
  except
    on E: Exception do
    begin
      Writeln(E.ClassName, ': ', E.Message);
      ExitCode := 1;
    end;
  end;
end.
