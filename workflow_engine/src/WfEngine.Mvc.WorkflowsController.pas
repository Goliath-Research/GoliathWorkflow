unit WfEngine.Mvc.WorkflowsController;

interface

uses
  MVCFramework,
  MVCFramework.Commons,
  WfEngine.GatewayDtos,
  WfEngine.GatewayService;

type
  [MVCPath('/v1/workflows')]
  TWorkflowsController = class(TMVCController)
  private
    FGateway: IGatewayService;
  public
    [MVCInject]
    constructor Create(const Gateway: IGatewayService); reintroduce;

    [MVCPath('/instances')]
    [MVCHTTPMethod([httpPOST])]
    function CreateInstance([MVCFromBody] Body: TCreateInstanceRequest): IMVCResponse;

    [MVCPath('/instances/($InstanceId)')]
    [MVCHTTPMethod([httpGET])]
    function GetInstance(const InstanceId: Int64): IMVCResponse;

    [MVCPath('/instances/($InstanceId)/start')]
    [MVCHTTPMethod([httpPOST])]
    function StartInstance(const InstanceId: Int64): IMVCResponse;

    [MVCPath('/definitions/($WorkflowName)')]
    [MVCHTTPMethod([httpDELETE])]
    function DeleteDefinition(const WorkflowName: string;
      [MVCFromQueryString('deleteInstances')] DeleteInstances: Boolean = True): IMVCResponse;
  end;

implementation

constructor TWorkflowsController.Create(const Gateway: IGatewayService);
begin
  inherited Create;
  FGateway := Gateway;
end;

function TWorkflowsController.CreateInstance(Body: TCreateInstanceRequest): IMVCResponse;
begin
  Result := CreatedResponse('', FGateway.CreateInstance(Body));
end;

function TWorkflowsController.GetInstance(const InstanceId: Int64): IMVCResponse;
begin
  Result := OKResponse(FGateway.GetInstance(InstanceId));
end;

function TWorkflowsController.StartInstance(const InstanceId: Int64): IMVCResponse;
begin
  Result := OKResponse(FGateway.StartInstance(InstanceId));
end;

function TWorkflowsController.DeleteDefinition(const WorkflowName: string;
  DeleteInstances: Boolean): IMVCResponse;
begin
  Result := OKResponse(FGateway.DeleteDefinition(WorkflowName, DeleteInstances));
end;

end.
