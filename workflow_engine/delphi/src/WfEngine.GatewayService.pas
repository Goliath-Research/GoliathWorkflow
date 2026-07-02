unit WfEngine.GatewayService;

{
  OpenAPI operation facade for the workflow REST gateway.
  One method per route; no HTTP path matching. Thread-safe via external lock.
  All database access goes through WfEngine.GatewayDb (stored procedures only).
}

interface

uses
  System.SysUtils,
  System.SyncObjs,
  WfEngine.GatewayDtos,
  WfEngine.ServiceLoop,
  WfEngine.Types;

type
  EActionSchemaNotFound = class(Exception);

  IGatewayService = interface
    ['{A7B3C4D2-8E1F-4A2B-9C0D-1E2F3A4B5C6D}']
    procedure WorkerAuthenticate(const ARequest: TWorkerAuthRequest);
    function RequestTask(const ARequest: TWorkerRequestTaskRequest): TWorkerTaskClaimResponse;
    function SubmitResult(const ANodeExecutionId: Int64;
      const ARequest: TWorkerSubmitResultRequest): TWorkerSubmitResultResponse;
    function Heartbeat(const ANodeExecutionId: Int64;
      const ARequest: TWorkerHeartbeatRequest): TWorkerHeartbeatResponse;
    procedure FailTask(const ANodeExecutionId: Int64; const ARequest: TWorkerFailTaskRequest);
    function CreateInstance(const ARequest: TCreateInstanceRequest): TWorkflowInstanceSummary;
    function GetInstance(const AInstanceId: Int64): TWorkflowInstanceSummary;
    function StartInstance(const AInstanceId: Int64): TWorkflowInstanceSummary;
    function DeleteDefinition(const AWorkflowName: string;
      ADeleteInstances: Boolean): TDeleteDefinitionResponse;
    function ListActions: TActionListResponse;
    function GetActionSchema(const AActionName, ADirection: string): TActionSchemaResponse;
  end;

  TGatewayService = class(TInterfacedObject, IGatewayService)
  private
    FSvc: TWorkflowEngineHostedService;
    FLock: TCriticalSection;
    procedure EnsureConnected;
    function InstanceSummary(const AInstanceId: Int64): TWorkflowInstanceSummary;
  public
    constructor Create(const ASvc: TWorkflowEngineHostedService; ALock: TCriticalSection);
    procedure WorkerAuthenticate(const ARequest: TWorkerAuthRequest);
    function RequestTask(const ARequest: TWorkerRequestTaskRequest): TWorkerTaskClaimResponse;
    function SubmitResult(const ANodeExecutionId: Int64;
      const ARequest: TWorkerSubmitResultRequest): TWorkerSubmitResultResponse;
    function Heartbeat(const ANodeExecutionId: Int64;
      const ARequest: TWorkerHeartbeatRequest): TWorkerHeartbeatResponse;
    procedure FailTask(const ANodeExecutionId: Int64; const ARequest: TWorkerFailTaskRequest);
    function CreateInstance(const ARequest: TCreateInstanceRequest): TWorkflowInstanceSummary;
    function GetInstance(const AInstanceId: Int64): TWorkflowInstanceSummary;
    function StartInstance(const AInstanceId: Int64): TWorkflowInstanceSummary;
    function DeleteDefinition(const AWorkflowName: string;
      ADeleteInstances: Boolean): TDeleteDefinitionResponse;
    function ListActions: TActionListResponse;
    function GetActionSchema(const AActionName, ADirection: string): TActionSchemaResponse;
  end;

implementation

uses
  System.JSON,
  WfEngine.GatewayDb;

{ TGatewayService }

constructor TGatewayService.Create(const ASvc: TWorkflowEngineHostedService;
  ALock: TCriticalSection);
begin
  inherited Create;
  FSvc := ASvc;
  FLock := ALock;
end;

procedure TGatewayService.EnsureConnected;
begin
  if not FSvc.Connection.Connected then
    FSvc.Connection.Connect;
end;

function TGatewayService.InstanceSummary(const AInstanceId: Int64): TWorkflowInstanceSummary;
var
  Row: TGatewayInstanceRow;
begin
  Row := GatewayGetWorkflowInstance(FSvc.Connection, AInstanceId);
  if not Row.Found then
    raise Exception.CreateFmt('Instance %d not found.', [AInstanceId]);
  Result := TWorkflowInstanceSummary.Create;
  Result.id := Row.Id;
  Result.workflow_version_id := Row.WorkflowVersionId;
  Result.status := Row.Status;
end;

procedure TGatewayService.WorkerAuthenticate(const ARequest: TWorkerAuthRequest);
begin
  FLock.Acquire;
  try
    EnsureConnected;
    GatewayWorkerAuthenticate(FSvc.Connection, ARequest.worker_id, ARequest.worker_token);
  finally
    FLock.Release;
  end;
end;

function TGatewayService.RequestTask(const ARequest: TWorkerRequestTaskRequest): TWorkerTaskClaimResponse;
var
  Claim: TWorkerTaskClaimResult;
  LeaseSec: Integer;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    if ARequest.max_lease_seconds > 0 then
      LeaseSec := ARequest.max_lease_seconds
    else
      LeaseSec := 300;
    Claim := FSvc.WorkerApi.RequestTask(
      ARequest.worker_id, ARequest.worker_token, ARequest.capability, LeaseSec);
    Result := TWorkerTaskClaimResponse.Create;
    Result.has_task := Claim.HasTask;
    if Claim.HasTask then
    begin
      Result.node_execution_id := Claim.NodeExecutionId;
      Result.workflow_instance_id := Claim.WorkflowInstanceId;
      Result.node_key := Claim.NodeKey;
      Result.action_name := Claim.ActionName;
      Result.capability := Claim.Capability;
      Result.attempt_no := Claim.AttemptNo;
      Result.input_json := TJSONObject.ParseJSONValue(Claim.InputJson);
      Result.iteration_no := Claim.IterationNo;
    end;
  finally
    FLock.Release;
  end;
end;

function TGatewayService.SubmitResult(const ANodeExecutionId: Int64;
  const ARequest: TWorkerSubmitResultRequest): TWorkerSubmitResultResponse;
var
  Ack: TSubmitResultAck;
  OutputJson: string;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    OutputJson := '';
    if Assigned(ARequest.output_json) then
      OutputJson := ARequest.output_json.ToJSON;
    Ack := FSvc.WorkerApi.SubmitResult(
      ANodeExecutionId, ARequest.worker_id, ARequest.worker_token,
      ARequest.result_code, OutputJson);
    Result := TWorkerSubmitResultResponse.Create;
    Result.accepted := Ack.Accepted;
    Result.instance_status := Ack.InstanceStatus.ToDb;
    Result.next_ready_count := Ack.NextReadyCount;
  finally
    FLock.Release;
  end;
end;

function TGatewayService.Heartbeat(const ANodeExecutionId: Int64;
  const ARequest: TWorkerHeartbeatRequest): TWorkerHeartbeatResponse;
var
  ExtendSec: Integer;
  RowsUpdated: Integer;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    if ARequest.extend_seconds > 0 then
      ExtendSec := ARequest.extend_seconds
    else
      ExtendSec := 300;
    RowsUpdated := FSvc.WorkerApi.Heartbeat(
      ANodeExecutionId, ARequest.worker_id, ARequest.worker_token, ExtendSec);
    Result := TWorkerHeartbeatResponse.Create;
    Result.rows_updated := RowsUpdated;
  finally
    FLock.Release;
  end;
end;

procedure TGatewayService.FailTask(const ANodeExecutionId: Int64;
  const ARequest: TWorkerFailTaskRequest);
begin
  FLock.Acquire;
  try
    EnsureConnected;
    FSvc.WorkerApi.FailTask(
      ANodeExecutionId, ARequest.worker_id, ARequest.worker_token,
      ARequest.error_code, ARequest.error_message);
  finally
    FLock.Release;
  end;
end;

function TGatewayService.CreateInstance(const ARequest: TCreateInstanceRequest): TWorkflowInstanceSummary;
var
  ContextJson: string;
  InstanceId: Int64;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    if Assigned(ARequest.context_json) then
      ContextJson := ARequest.context_json.ToJSON
    else
      ContextJson := '{}';
    InstanceId := FSvc.CreateAndStartInstance(ARequest.workflow_version_id, ContextJson);
    Result := InstanceSummary(InstanceId);
  finally
    FLock.Release;
  end;
end;

function TGatewayService.GetInstance(const AInstanceId: Int64): TWorkflowInstanceSummary;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    Result := InstanceSummary(AInstanceId);
  finally
    FLock.Release;
  end;
end;

function TGatewayService.StartInstance(const AInstanceId: Int64): TWorkflowInstanceSummary;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    FSvc.StartInstance(AInstanceId);
    Result := InstanceSummary(AInstanceId);
  finally
    FLock.Release;
  end;
end;

function TGatewayService.DeleteDefinition(const AWorkflowName: string;
  ADeleteInstances: Boolean): TDeleteDefinitionResponse;
var
  Row: TGatewayDeleteDefRow;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    Row := GatewayDeleteWorkflowDefinition(FSvc.Connection, AWorkflowName, ADeleteInstances);
    Result := TDeleteDefinitionResponse.Create;
    Result.deleted_instance_count := Row.DeletedInstanceCount;
    Result.deleted_version_count := Row.DeletedVersionCount;
  finally
    FLock.Release;
  end;
end;

function TGatewayService.ListActions: TActionListResponse;
var
  Rows: TArray<TGatewayActionRow>;
  Item: TActionSummary;
  Items: TArray<TActionSummary>;
  I: Integer;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    Rows := GatewayListActions(FSvc.Connection);
    Result := TActionListResponse.Create;
    SetLength(Items, Length(Rows));
    for I := 0 to High(Rows) do
    begin
      Item := TActionSummary.Create;
      Item.action_name := Rows[I].ActionName;
      Item.capability := Rows[I].Capability;
      Item.has_input_schema := Rows[I].HasInputSchema;
      Item.has_output_schema := Rows[I].HasOutputSchema;
      Items[I] := Item;
    end;
    Result.actions := Items;
  finally
    FLock.Release;
  end;
end;

function TGatewayService.GetActionSchema(const AActionName, ADirection: string): TActionSchemaResponse;
var
  Row: TGatewayActionSchemaRow;
  SchemaVal: TJSONValue;
begin
  if not SameText(ADirection, 'input') and not SameText(ADirection, 'output') then
    raise Exception.Create('direction must be input or output');

  FLock.Acquire;
  try
    EnsureConnected;
    Row := GatewayGetActionSchema(FSvc.Connection, AActionName, ADirection);
    if not Row.Found then
      raise EActionSchemaNotFound.CreateFmt('schema not found for %s (%s)', [AActionName, ADirection]);

    Result := TActionSchemaResponse.Create;
    Result.action_name := Row.ActionName;
    Result.direction := Row.Direction;
    Result.schema_id := Row.SchemaId;
    SchemaVal := TJSONObject.ParseJSONValue(Row.SchemaJson);
    if SchemaVal = nil then
      SchemaVal := TJSONObject.Create;
    Result.schema_json := SchemaVal;
  finally
    FLock.Release;
  end;
end;

end.
