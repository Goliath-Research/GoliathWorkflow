unit WfEngine.ServiceLoop;

interface

uses
  System.SysUtils,
  Uni,
  WfEngine.Connection,
  WfEngine.GatewayDb,
  WfEngine.Interfaces,
  WfEngine.WorkerApiAdapter;

type
  TWorkflowEngineServiceConfig = record
    Connection: TConnectionConfig;
  end;

  TWorkflowEngineHostedService = class
  private
    FConnection: TUniConnection;
    FWorkerApi: IWorkflowWorkerApi;
    FConfig: TWorkflowEngineServiceConfig;
    procedure EnsureConnected;
  public
    constructor Create(const AConfig: TWorkflowEngineServiceConfig);
    destructor Destroy; override;
    procedure StartInstance(const AWorkflowInstanceId: Int64);
    function CreateAndStartInstance(const AVersionId: Int64; const AContextJson: string): Int64;
    procedure Stop;
    property WorkerApi: IWorkflowWorkerApi read FWorkerApi;
    property Connection: TUniConnection read FConnection;
  end;

implementation

{ TWorkflowEngineHostedService }

constructor TWorkflowEngineHostedService.Create(const AConfig: TWorkflowEngineServiceConfig);
begin
  inherited Create;
  FConfig := AConfig;
  FConnection := TUniConnection.Create(nil);
  ConfigureUniConnection(FConnection, FConfig.Connection);
  FWorkerApi := TWorkflowWorkerApi.Create(FConnection);
end;

destructor TWorkflowEngineHostedService.Destroy;
begin
  Stop;
  FConnection.Free;
  inherited;
end;

procedure TWorkflowEngineHostedService.EnsureConnected;
begin
  ConnectUniDatabase(FConnection, FConfig.Connection);
end;

procedure TWorkflowEngineHostedService.StartInstance(const AWorkflowInstanceId: Int64);
begin
  EnsureConnected;
  GatewayStartWorkflowInstance(FConnection, AWorkflowInstanceId);
end;

function TWorkflowEngineHostedService.CreateAndStartInstance(const AVersionId: Int64;
  const AContextJson: string): Int64;
begin
  EnsureConnected;
  Result := GatewayCreateWorkflowInstance(FConnection, AVersionId, AContextJson);
  GatewayStartWorkflowInstance(FConnection, Result);
end;

procedure TWorkflowEngineHostedService.Stop;
begin
  if FConnection.Connected then
    FConnection.Disconnect;
end;

end.
