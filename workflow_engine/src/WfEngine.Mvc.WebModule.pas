unit WfEngine.Mvc.WebModule;

{
  WebBroker module hosting the DMVC engine for the workflow gateway.
  Used by both the Windows service host and the console debug mode
  through TIdHTTPWebBrokerBridge.
}

interface

uses
  System.SysUtils,
  System.Classes,
  Web.HTTPApp,
  MVCFramework;

type
  TWfGatewayWebModule = class(TWebModule)
    procedure WebModuleCreate(Sender: TObject);
    procedure WebModuleDestroy(Sender: TObject);
  private
    FMVC: TMVCEngine;
  end;

var
  WebModuleClass: TComponentClass = TWfGatewayWebModule;

implementation

{%CLASSGROUP 'System.Classes.TPersistent'}

{$R *.dfm}

uses
  MVCFramework.Commons,
  WfEngine.Mvc.Controller;

procedure TWfGatewayWebModule.WebModuleCreate(Sender: TObject);
begin
  FMVC := TMVCEngine.Create(Self,
    procedure(Config: TMVCConfig)
    begin
      Config[TMVCConfigKey.DefaultContentType] := TMVCMediaType.APPLICATION_JSON;
      Config[TMVCConfigKey.DefaultContentCharset] := TMVCCharSet.UTF_8;
      Config[TMVCConfigKey.LoadSystemControllers] := 'false';
    end);
  FMVC.AddController(TWfGatewayController);
end;

procedure TWfGatewayWebModule.WebModuleDestroy(Sender: TObject);
begin
  FMVC.Free;
end;

end.
