unit WfEngine.ServiceLoop;

interface

uses
  System.SysUtils,
  System.Classes,
  System.DateUtils,
  Uni,
  WfEngine.Interfaces,
  WfEngine.Scheduler,
  WfEngine.Types,
  WfEngine.WorkerApiAdapter;

type
  TWorkflowEngineServiceConfig = record
    PollIntervalMs: Integer;
    MaxInstancesPerTick: Integer;
    ConnectionString: string;
    UseEngineSubmitPath: Boolean;
  end;

  TWorkflowEngineHostedService = class
  private
    FConnection: TUniConnection;
    FEngine: IWorkflowEngine;
    FWorkerApi: IWorkflowWorkerApi;
    FConfig: TWorkflowEngineServiceConfig;
    FRunning: Boolean;
    procedure EnsureConnected;
  public
    constructor Create(const AConfig: TWorkflowEngineServiceConfig);
    destructor Destroy; override;
    procedure StartInstance(const AWorkflowInstanceId: Int64);
    function CreateAndStartInstance(const AVersionId: Int64; const AContextJson: string): Int64;
    procedure RunOnce;
    procedure RunUntilStopped;
    procedure Stop;
    property Engine: IWorkflowEngine read FEngine;
    property WorkerApi: IWorkflowWorkerApi read FWorkerApi;
  end;

implementation

{ TWorkflowEngineHostedService }

constructor TWorkflowEngineHostedService.Create(const AConfig: TWorkflowEngineServiceConfig);
begin
  inherited Create;
  FConfig := AConfig;
  if FConfig.PollIntervalMs <= 0 then
    FConfig.PollIntervalMs := 1000;
  if FConfig.MaxInstancesPerTick <= 0 then
    FConfig.MaxInstancesPerTick := 50;
  FConnection := TUniConnection.Create(nil);
  FConnection.ConnectString := FConfig.ConnectionString;
  FEngine := TWorkflowEngine.Create(FConnection);
  if FConfig.UseEngineSubmitPath then
    FWorkerApi := TWorkflowWorkerApi.Create(FConnection, FEngine)
  else
    FWorkerApi := TWorkflowWorkerApi.Create(FConnection, nil);
  FRunning := False;
end;

destructor TWorkflowEngineHostedService.Destroy;
begin
  Stop;
  FConnection.Free;
  inherited;
end;

procedure TWorkflowEngineHostedService.EnsureConnected;
begin
  if not FConnection.Connected then
    FConnection.Connect;
end;

procedure TWorkflowEngineHostedService.StartInstance(const AWorkflowInstanceId: Int64);
begin
  EnsureConnected;
  TWorkflowEngine(FEngine).StartInstance(AWorkflowInstanceId);
end;

function TWorkflowEngineHostedService.CreateAndStartInstance(const AVersionId: Int64;
  const AContextJson: string): Int64;
begin
  EnsureConnected;
  Result := TWorkflowEngine(FEngine).Repository.CreateWorkflowInstance(
    AVersionId, AContextJson);
  FEngine.StartInstance(Result);
end;

procedure TWorkflowEngineHostedService.RunOnce;
var
  Tick: TSchedulerTickResult;
begin
  EnsureConnected;
  Tick := FEngine.RunSchedulerTick(FConfig.MaxInstancesPerTick);
end;

procedure TWorkflowEngineHostedService.RunUntilStopped;
begin
  FRunning := True;
  EnsureConnected;
  while FRunning do
  begin
    RunOnce;
    Sleep(FConfig.PollIntervalMs);
  end;
end;

procedure TWorkflowEngineHostedService.Stop;
begin
  FRunning := False;
  if FConnection.Connected then
    FConnection.Disconnect;
end;

end.
