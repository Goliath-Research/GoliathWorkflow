unit WfEngine.RestHttpServer;

{
  Indy HTTP server exposing OpenAPI routes via TRestApiService.
  Build with Indy (IdHTTPWebBrokerBridge / IdCustomHTTPServer) packages enabled.
}

interface

uses
  System.Classes,
  System.SysUtils,
  IdContext,
  IdCustomHTTPServer,
  IdHTTPHeaderInfo,
  IdHTTPServer,
  WfEngine.RestApi,
  WfEngine.ServiceLoop;

type
  TRestHttpServer = class
  private
    FServer: TIdHTTPServer;
    FApi: TRestApiService;
    procedure DoCommandGet(AContext: TIdContext; ARequestInfo: TIdHTTPRequestInfo;
      AResponseInfo: TIdHTTPResponseInfo);
  public
    constructor Create(const ASvc: TWorkflowEngineHostedService);
    destructor Destroy; override;
    procedure Start(APort: Integer);
    procedure Stop;
  end;

implementation

{ TRestHttpServer }

constructor TRestHttpServer.Create(const ASvc: TWorkflowEngineHostedService);
begin
  inherited Create;
  FApi := TRestApiService.Create(ASvc);
  FServer := TIdHTTPServer.Create(nil);
  FServer.OnCommandGet := DoCommandGet;
  FServer.OnCommandOther := DoCommandGet;
end;

destructor TRestHttpServer.Destroy;
begin
  Stop;
  FServer.Free;
  FApi.Free;
  inherited;
end;

procedure TRestHttpServer.DoCommandGet(AContext: TIdContext; ARequestInfo: TIdHTTPRequestInfo;
  AResponseInfo: TIdHTTPResponseInfo);
var
  Status: Integer;
  Body, ResponseBody: string;
  Stream: TStream;
begin
  Body := '';
  if Assigned(ARequestInfo.PostStream) and (ARequestInfo.PostStream.Size > 0) then
  begin
    ARequestInfo.PostStream.Position := 0;
    Stream := ARequestInfo.PostStream;
    var Bytes: TBytes;
    SetLength(Bytes, Stream.Size);
    Stream.ReadBuffer(Bytes[0], Stream.Size);
    Body := TEncoding.UTF8.GetString(Bytes);
  end;

  ResponseBody := FApi.Handle(ARequestInfo.Command, ARequestInfo.Document, Body, Status);
  AResponseInfo.ResponseNo := Status;
  if Status = 204 then
    Exit;
  AResponseInfo.ContentType := 'application/json';
  AResponseInfo.ContentText := ResponseBody;
end;

procedure TRestHttpServer.Start(APort: Integer);
begin
  FServer.DefaultPort := APort;
  FServer.Active := True;
  Writeln(Format('REST API listening on http://0.0.0.0:%d/v1', [APort]));
end;

procedure TRestHttpServer.Stop;
begin
  if FServer.Active then
    FServer.Active := False;
end;

end.
