unit WfEngine.GatewayHost;

{
  Process-wide gateway state shared by the Windows service host and the
  DMVC controller (WfEngine.Mvc.Controller).

  Owns the single UniDAC-backed TWorkflowEngineHostedService and the
  TRestApiService contract dispatcher. DMVC serves requests from a thread
  pool, while the gateway uses one shared DB connection, so dispatch is
  serialized with a critical section.
}

interface

procedure InitGatewayHost(const AConnectionString: string);
procedure ShutdownGatewayHost;
function GatewayHostInitialized: Boolean;

function HandleGatewayRequest(const AMethod, APath, ABody: string;
  out AStatus: Integer): string;

function ResolveGatewayConnectionString: string;
function ResolveGatewayPort(const ADefault: Integer = 8080): Integer;

implementation

uses
  System.SysUtils,
  System.SyncObjs,
  WfEngine.Dialect,
  WfEngine.RestApi,
  WfEngine.ServiceLoop;

var
  GLock: TCriticalSection;
  GSvc: TWorkflowEngineHostedService;
  GApi: TRestApiService;

function ResolveGatewayConnectionString: string;
begin
  Result := GetEnvironmentVariable('METHYLPIPELINE_DB');
  if Result = '' then
    Result := BuildConnectionStringFromEnv;
  if Result = '' then
    raise Exception.Create(
      'Set METHYLPIPELINE_DB or POSTGRES_*/AZURE_SQL_* environment variables.');
end;

function ResolveGatewayPort(const ADefault: Integer): Integer;
begin
  Result := StrToIntDef(GetEnvironmentVariable('WF_GATEWAY_PORT'), ADefault);
end;

procedure InitGatewayHost(const AConnectionString: string);
var
  Cfg: TWorkflowEngineServiceConfig;
begin
  GLock.Acquire;
  try
    if GSvc <> nil then
      Exit;
    Cfg.ConnectionString := AConnectionString;
    GSvc := TWorkflowEngineHostedService.Create(Cfg);
    GApi := TRestApiService.Create(GSvc);
  finally
    GLock.Release;
  end;
end;

procedure ShutdownGatewayHost;
begin
  GLock.Acquire;
  try
    FreeAndNil(GApi);
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

function HandleGatewayRequest(const AMethod, APath, ABody: string;
  out AStatus: Integer): string;
begin
  GLock.Acquire;
  try
    if GApi = nil then
    begin
      AStatus := 503;
      Exit('{"error":"gateway not initialized"}');
    end;
    Result := GApi.Handle(AMethod, APath, ABody, AStatus);
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
