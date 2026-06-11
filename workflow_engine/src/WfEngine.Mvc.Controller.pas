unit WfEngine.Mvc.Controller;

{
  DelphiMVCFramework controller for the workflow REST gateway.
  Routes mirror contracts/openapi.yaml; every action delegates to the
  shared TRestApiService dispatcher (WfEngine.GatewayHost), which calls
  the wf SQL contract procedures.
}

interface

uses
  MVCFramework,
  MVCFramework.Commons;

type
  [MVCPath('/v1')]
  TWfGatewayController = class(TMVCController)
  private
    procedure Delegate;
  public
    [MVCPath('/workers/authenticate')]
    [MVCHTTPMethod([httpPOST])]
    procedure WorkerAuthenticate;

    [MVCPath('/workers/tasks/request')]
    [MVCHTTPMethod([httpPOST])]
    procedure WorkerRequestTask;

    [MVCPath('/workers/tasks/($NodeExecutionId)/submit')]
    [MVCHTTPMethod([httpPOST])]
    procedure WorkerSubmitResult(const NodeExecutionId: Int64);

    [MVCPath('/workers/tasks/($NodeExecutionId)/heartbeat')]
    [MVCHTTPMethod([httpPOST])]
    procedure WorkerHeartbeat(const NodeExecutionId: Int64);

    [MVCPath('/workers/tasks/($NodeExecutionId)/fail')]
    [MVCHTTPMethod([httpPOST])]
    procedure WorkerFailTask(const NodeExecutionId: Int64);

    [MVCPath('/workflows/instances')]
    [MVCHTTPMethod([httpPOST])]
    procedure CreateInstance;

    [MVCPath('/workflows/instances/($InstanceId)')]
    [MVCHTTPMethod([httpGET])]
    procedure GetInstance(const InstanceId: Int64);

    [MVCPath('/workflows/instances/($InstanceId)/start')]
    [MVCHTTPMethod([httpPOST])]
    procedure StartInstance(const InstanceId: Int64);

    [MVCPath('/workflows/definitions/($WorkflowName)')]
    [MVCHTTPMethod([httpDELETE])]
    procedure DeleteDefinition(const WorkflowName: string);

    [MVCPath('/actions')]
    [MVCHTTPMethod([httpGET])]
    procedure ListActions;

    [MVCPath('/actions/($ActionName)/schema')]
    [MVCHTTPMethod([httpGET])]
    procedure GetActionSchema(const ActionName: string);
  end;

implementation

uses
  WfEngine.GatewayHost;

{ TWfGatewayController }

procedure TWfGatewayController.Delegate;
var
  Status: Integer;
  Payload: string;
begin
  // Backend-agnostic request access (works for HTTP.sys, Indy, WebBroker).
  Payload := HandleGatewayRequest(
    Context.Request.HTTPMethodAsString,
    Context.Request.PathInfo,
    Context.Request.Query,
    Context.Request.Body,
    Status);
  Context.Response.StatusCode := Status;
  ContentType := TMVCMediaType.APPLICATION_JSON;
  if Status = 204 then
    Render('')
  else
    Render(Payload);
end;

procedure TWfGatewayController.WorkerAuthenticate;
begin
  Delegate;
end;

procedure TWfGatewayController.WorkerRequestTask;
begin
  Delegate;
end;

procedure TWfGatewayController.WorkerSubmitResult(const NodeExecutionId: Int64);
begin
  Delegate;
end;

procedure TWfGatewayController.WorkerHeartbeat(const NodeExecutionId: Int64);
begin
  Delegate;
end;

procedure TWfGatewayController.WorkerFailTask(const NodeExecutionId: Int64);
begin
  Delegate;
end;

procedure TWfGatewayController.CreateInstance;
begin
  Delegate;
end;

procedure TWfGatewayController.GetInstance(const InstanceId: Int64);
begin
  Delegate;
end;

procedure TWfGatewayController.StartInstance(const InstanceId: Int64);
begin
  Delegate;
end;

procedure TWfGatewayController.DeleteDefinition(const WorkflowName: string);
begin
  Delegate;
end;

procedure TWfGatewayController.ListActions;
begin
  Delegate;
end;

procedure TWfGatewayController.GetActionSchema(const ActionName: string);
begin
  Delegate;
end;

end.
