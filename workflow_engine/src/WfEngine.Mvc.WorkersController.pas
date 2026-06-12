unit WfEngine.Mvc.WorkersController;

interface

uses
  MVCFramework,
  MVCFramework.Commons,
  WfEngine.GatewayDtos,
  WfEngine.GatewayService;

type
  [MVCPath('/v1/workers')]
  TWorkersController = class(TMVCController)
  private
    FGateway: IGatewayService;
  public
    [MVCInject]
    constructor Create(const Gateway: IGatewayService); reintroduce;

    [MVCPath('/authenticate')]
    [MVCHTTPMethod([httpPOST])]
    function Authenticate([MVCFromBody] Body: TWorkerAuthRequest): IMVCResponse;

    [MVCPath('/tasks/request')]
    [MVCHTTPMethod([httpPOST])]
    function RequestTask([MVCFromBody] Body: TWorkerRequestTaskRequest): IMVCResponse;

    [MVCPath('/tasks/($NodeExecutionId)/submit')]
    [MVCHTTPMethod([httpPOST])]
    function SubmitResult(const NodeExecutionId: Int64;
      [MVCFromBody] Body: TWorkerSubmitResultRequest): IMVCResponse;

    [MVCPath('/tasks/($NodeExecutionId)/heartbeat')]
    [MVCHTTPMethod([httpPOST])]
    function Heartbeat(const NodeExecutionId: Int64;
      [MVCFromBody] Body: TWorkerHeartbeatRequest): IMVCResponse;

    [MVCPath('/tasks/($NodeExecutionId)/fail')]
    [MVCHTTPMethod([httpPOST])]
    function FailTask(const NodeExecutionId: Int64;
      [MVCFromBody] Body: TWorkerFailTaskRequest): IMVCResponse;
  end;

implementation

constructor TWorkersController.Create(const Gateway: IGatewayService);
begin
  inherited Create;
  FGateway := Gateway;
end;

function TWorkersController.Authenticate(Body: TWorkerAuthRequest): IMVCResponse;
begin
  FGateway.WorkerAuthenticate(Body);
  Result := OKResponse(TJSONObject.Create);
end;

function TWorkersController.RequestTask(Body: TWorkerRequestTaskRequest): IMVCResponse;
begin
  Result := OKResponse(FGateway.RequestTask(Body));
end;

function TWorkersController.SubmitResult(const NodeExecutionId: Int64;
  Body: TWorkerSubmitResultRequest): IMVCResponse;
begin
  Result := OKResponse(FGateway.SubmitResult(NodeExecutionId, Body));
end;

function TWorkersController.Heartbeat(const NodeExecutionId: Int64;
  Body: TWorkerHeartbeatRequest): IMVCResponse;
begin
  Result := OKResponse(FGateway.Heartbeat(NodeExecutionId, Body));
end;

function TWorkersController.FailTask(const NodeExecutionId: Int64;
  Body: TWorkerFailTaskRequest): IMVCResponse;
begin
  FGateway.FailTask(NodeExecutionId, Body);
  Result := NoContentResponse;
end;

end.
