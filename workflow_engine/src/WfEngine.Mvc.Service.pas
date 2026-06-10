unit WfEngine.Mvc.Service;

{
  Windows service host for the DMVC workflow gateway.

  Service name: MethylWfGateway
  - Start    -> open DB-backed gateway state and HTTP listener
  - Pause    -> stop accepting HTTP requests (DB state kept)
  - Continue -> resume the HTTP listener
  - Stop     -> close listener and release gateway state

  Install/uninstall with the standard VCL service switches:
    WfEngineSrv /install
    WfEngineSrv /uninstall
}

interface

uses
  Winapi.Windows,
  System.SysUtils,
  System.Classes,
  Vcl.SvcMgr,
  IdHTTPWebBrokerBridge;

type
  TMethylWfGatewayService = class(TService)
    procedure ServiceStart(Sender: TService; var Started: Boolean);
    procedure ServiceStop(Sender: TService; var Stopped: Boolean);
    procedure ServicePause(Sender: TService; var Paused: Boolean);
    procedure ServiceContinue(Sender: TService; var Continued: Boolean);
  private
    FBridge: TIdHTTPWebBrokerBridge;
  public
    function GetServiceController: TServiceController; override;
  end;

var
  MethylWfGateway: TMethylWfGatewayService;

implementation

{$R *.dfm}

uses
  Web.WebReq,
  WfEngine.GatewayHost,
  WfEngine.Mvc.WebModule;

procedure ServiceController(CtrlCode: DWORD); stdcall;
begin
  MethylWfGateway.Controller(CtrlCode);
end;

function TMethylWfGatewayService.GetServiceController: TServiceController;
begin
  Result := ServiceController;
end;

procedure TMethylWfGatewayService.ServiceStart(Sender: TService; var Started: Boolean);
begin
  Started := False;
  try
    if WebRequestHandler <> nil then
      WebRequestHandler.WebModuleClass := WebModuleClass;
    InitGatewayHost(ResolveGatewayConnectionString);
    FBridge := TIdHTTPWebBrokerBridge.Create(nil);
    FBridge.DefaultPort := ResolveGatewayPort;
    FBridge.Active := True;
    Started := True;
  except
    on E: Exception do
    begin
      LogMessage(Format('MethylWfGateway start failed: %s: %s', [E.ClassName, E.Message]));
      FreeAndNil(FBridge);
      ShutdownGatewayHost;
    end;
  end;
end;

procedure TMethylWfGatewayService.ServiceStop(Sender: TService; var Stopped: Boolean);
begin
  if Assigned(FBridge) then
  begin
    FBridge.Active := False;
    FreeAndNil(FBridge);
  end;
  ShutdownGatewayHost;
  Stopped := True;
end;

procedure TMethylWfGatewayService.ServicePause(Sender: TService; var Paused: Boolean);
begin
  if Assigned(FBridge) then
    FBridge.Active := False;
  Paused := True;
end;

procedure TMethylWfGatewayService.ServiceContinue(Sender: TService; var Continued: Boolean);
begin
  if Assigned(FBridge) then
    FBridge.Active := True;
  Continued := True;
end;

end.
