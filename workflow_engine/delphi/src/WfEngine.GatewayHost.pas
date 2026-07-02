unit WfEngine.GatewayHost;

{
  Process-wide gateway state shared by the Windows service host and DMVC controllers.

  Owns the single UniDAC-backed TWorkflowEngineHostedService and IGatewayService.
  DMVC serves requests from a thread pool; the gateway service serializes DB access.
}

interface

uses
  WfEngine.Connection,
  WfEngine.GatewayService;

procedure InitGatewayHost(const AConnection: TConnectionConfig);
procedure ShutdownGatewayHost;
function GatewayHostInitialized: Boolean;
function GetGatewayService: IGatewayService;

function ResolveGatewayConnectionConfig: TConnectionConfig;
function ResolveGatewayConnectionString: string;
function ResolveGatewayPort(const ADefault: Integer = 8080): Integer;

implementation

uses
  System.SysUtils,
  System.SyncObjs,
  WfEngine.ServiceLoop;

var
  GLock: TCriticalSection;
  GSvc: TWorkflowEngineHostedService;
  GGateway: IGatewayService;

function ResolveGatewayConnectionConfig: TConnectionConfig;
begin
  Result := ResolveConnectionConfig;
  if Result.ConnectionString = '' then
    raise Exception.Create(
      'Set METHYLPIPELINE_DB or POSTGRES_*/AZURE_SQL_* environment variables.');
end;

function ResolveGatewayConnectionString: string;
begin
  Result := ResolveGatewayConnectionConfig.ConnectionString;
end;

function ResolveGatewayPort(const ADefault: Integer): Integer;
begin
  Result := StrToIntDef(GetEnvironmentVariable('WF_GATEWAY_PORT'), ADefault);
end;

procedure InitGatewayHost(const AConnection: TConnectionConfig);
var
  Cfg: TWorkflowEngineServiceConfig;
begin
  GLock.Acquire;
  try
    if GSvc <> nil then
      Exit;
    Cfg.Connection := AConnection;
    GSvc := TWorkflowEngineHostedService.Create(Cfg);
    GGateway := TGatewayService.Create(GSvc, GLock);
  finally
    GLock.Release;
  end;
end;

procedure ShutdownGatewayHost;
begin
  GLock.Acquire;
  try
    GGateway := nil;
    FreeAndNil(GSvc);
  finally
    GLock.Release;
  end;
end;

function GatewayHostInitialized: Boolean;
begin
  GLock.Acquire;
  try
    Result := GSvc <> nil;
  finally
    GLock.Release;
  end;
end;

function GetGatewayService: IGatewayService;
begin
  GLock.Acquire;
  try
    if GGateway = nil then
      raise Exception.Create('Gateway not initialized');
    Result := GGateway;
  finally
    GLock.Release;
  end;
end;

initialization
  GLock := TCriticalSection.Create;

finalization
  ShutdownGatewayHost;
  FreeAndNil(GLock);

end.
