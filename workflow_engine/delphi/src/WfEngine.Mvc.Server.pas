unit WfEngine.Mvc.Server;

{
  Engine-first DMVC server construction for the workflow gateway.

  Uses the pluggable IMVCServer backend (DMVC 3.5+) with the HTTP.sys
  kernel-mode driver (TMVCServerFactory.CreateHttpSys).
}

interface

uses
  System.SysUtils,
  MVCFramework,
  MVCFramework.Server.Intf;

type
  TWfGatewayServer = class
  private
    FEngine: TMVCEngine;
    FServer: IMVCServer;
    FPort: Integer;
    FHost: string;
  public
    constructor Create(const APort: Integer; const AHost: string);
    destructor Destroy; override;
    procedure Start;
    procedure Stop;
    function IsRunning: Boolean;
    property Port: Integer read FPort;
    property Host: string read FHost;
  end;

function ResolveGatewayHost(const ADefault: string): string;

implementation

uses
  MVCFramework.Commons,
  MVCFramework.Server.Factory,
  WfEngine.GatewayHost,
  WfEngine.Mvc.ActionsController,
  WfEngine.Mvc.WorkersController,
  WfEngine.Mvc.WorkflowsController;

function ResolveGatewayHost(const ADefault: string): string;
begin
  Result := GetEnvironmentVariable('WF_GATEWAY_HOST');
  if Result = '' then
    Result := ADefault;
end;

{ TWfGatewayServer }

constructor TWfGatewayServer.Create(const APort: Integer; const AHost: string);
begin
  inherited Create;
  FPort := APort;
  FHost := AHost;
  if not GatewayHostInitialized then
    raise Exception.Create('Gateway host must be initialized before starting HTTP server.');

  FEngine := TMVCEngine.Create(nil,
    procedure(Config: TMVCConfig)
    begin
      Config[TMVCConfigKey.DefaultContentType] := TMVCMediaType.APPLICATION_JSON;
      Config[TMVCConfigKey.DefaultContentCharset] := TMVCCharSet.UTF_8;
      Config[TMVCConfigKey.LoadSystemControllers] := 'false';
    end);

  FEngine.AddController(TWorkersController);
  FEngine.AddController(TWorkflowsController);
  FEngine.AddController(TActionsController);
  FServer := TMVCServerFactory.CreateHttpSys(FEngine);
end;

destructor TWfGatewayServer.Destroy;
begin
  Stop;
  FServer := nil;
  FEngine.Free;
  inherited;
end;

procedure TWfGatewayServer.Start;
begin
  if not FServer.IsRunning then
    FServer.Listen(FPort, FHost);
end;

procedure TWfGatewayServer.Stop;
begin
  if (FServer <> nil) and FServer.IsRunning then
    FServer.Stop;
end;

function TWfGatewayServer.IsRunning: Boolean;
begin
  Result := (FServer <> nil) and FServer.IsRunning;
end;

end.
