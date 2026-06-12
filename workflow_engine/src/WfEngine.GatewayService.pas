unit WfEngine.GatewayService;

{
  OpenAPI operation facade for the workflow REST gateway.
  One method per route; no HTTP path matching. Thread-safe via external lock.
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
  Data.DB,
  System.JSON,
  Uni,
  WfEngine.Dialect;

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
  Q: TUniQuery;
begin
  Q := TUniQuery.Create(nil);
  try
    Q.Connection := FSvc.Connection;
    Q.SQL.Text := Format(
      'SELECT id, workflow_version_id, status FROM %sworkflow_instance WHERE id = :id',
      [WfSchemaDot]);
    Q.ParamByName('id').AsLargeInt := AInstanceId;
    Q.Open;
    if Q.Eof then
      raise Exception.CreateFmt('Instance %d not found.', [AInstanceId]);
    Result := TWorkflowInstanceSummary.Create;
    Result.id := Q.FieldByName('id').AsLargeInt;
    Result.workflow_version_id := Q.FieldByName('workflow_version_id').AsLargeInt;
    Result.status := Q.FieldByName('status').AsString;
  finally
    Q.Free;
  end;
end;

procedure TGatewayService.WorkerAuthenticate(const ARequest: TWorkerAuthRequest);
var
  P: TUniStoredProc;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    P := TUniStoredProc.Create(nil);
    try
      P.Connection := FSvc.Connection;
      P.StoredProcName := WfSchemaDot + 'wf_worker_authenticate';
      P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := ARequest.worker_id;
      P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := ARequest.worker_token;
      P.ExecProc;
    finally
      P.Free;
    end;
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
  P: TUniStoredProc;
  Q: TUniQuery;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    Result := TDeleteDefinitionResponse.Create;
    Result.deleted_instance_count := 0;
    Result.deleted_version_count := 0;
    if GetWorkflowBackend = wbPostgres then
    begin
      Q := TUniQuery.Create(nil);
      try
        Q.Connection := FSvc.Connection;
        Q.SQL.Text := Format(
          'SELECT deleted_instance_count, deleted_version_count FROM %ssp_delete_workflow_def(NULL, :name, :del)',
          [WfSchemaDot]);
        Q.ParamByName('name').AsString := AWorkflowName;
        Q.ParamByName('del').AsBoolean := ADeleteInstances;
        Q.Open;
        if not Q.Eof then
        begin
          Result.deleted_instance_count := Q.FieldByName('deleted_instance_count').AsInteger;
          Result.deleted_version_count := Q.FieldByName('deleted_version_count').AsInteger;
        end;
      finally
        Q.Free;
      end;
    end
    else
    begin
      P := TUniStoredProc.Create(nil);
      try
        P.Connection := FSvc.Connection;
        P.StoredProcName := WfSchemaDot + 'sp_delete_workflow_def';
        P.Params.CreateParam(ftLargeint, 'workflow_def_id', ptInput).Clear;
        P.Params.CreateParam(ftWideString, 'workflow_name', ptInput).AsString := AWorkflowName;
        P.Params.CreateParam(ftBoolean, 'delete_instances', ptInput).AsBoolean := ADeleteInstances;
        P.Open;
        if not P.Eof then
        begin
          Result.deleted_instance_count := P.FieldByName('deleted_instance_count').AsInteger;
          Result.deleted_version_count := P.FieldByName('deleted_version_count').AsInteger;
        end;
      finally
        P.Free;
      end;
    end;
  finally
    FLock.Release;
  end;
end;

function TGatewayService.ListActions: TActionListResponse;
var
  Q: TUniQuery;
  Item: TActionSummary;
  Items: TArray<TActionSummary>;
  I: Integer;
begin
  FLock.Acquire;
  try
    EnsureConnected;
    Result := TActionListResponse.Create;
    Q := TUniQuery.Create(nil);
    try
      Q.Connection := FSvc.Connection;
      Q.SQL.Text := Format('SELECT * FROM %swf_repo_list_actions()', [WfSchemaDot]);
      Q.Open;
      SetLength(Items, 0);
      while not Q.Eof do
      begin
        Item := TActionSummary.Create;
        Item.action_name := Q.FieldByName('action_name').AsString;
        if Q.FieldByName('capability').IsNull then
          Item.capability := ''
        else
          Item.capability := Q.FieldByName('capability').AsString;
        Item.has_input_schema := Q.FieldByName('has_input_schema').AsBoolean;
        Item.has_output_schema := Q.FieldByName('has_output_schema').AsBoolean;
        I := Length(Items);
        SetLength(Items, I + 1);
        Items[I] := Item;
        Q.Next;
      end;
      Result.actions := Items;
    finally
      Q.Free;
    end;
  finally
    FLock.Release;
  end;
end;

function TGatewayService.GetActionSchema(const AActionName, ADirection: string): TActionSchemaResponse;
var
  Q: TUniQuery;
  SchemaText: string;
  SchemaVal: TJSONValue;
begin
  if not SameText(ADirection, 'input') and not SameText(ADirection, 'output') then
    raise Exception.Create('direction must be input or output');

  FLock.Acquire;
  try
    EnsureConnected;
    Q := TUniQuery.Create(nil);
    try
      Q.Connection := FSvc.Connection;
      Q.SQL.Text := Format(
        'SELECT action_name, direction, schema_id, schema_json FROM %swf_repo_get_action_schema(:name, :dir)',
        [WfSchemaDot]);
      Q.ParamByName('name').AsString := AActionName;
      Q.ParamByName('dir').AsString := ADirection;
      Q.Open;
      if Q.Eof then
        raise EActionSchemaNotFound.CreateFmt('schema not found for %s (%s)', [AActionName, ADirection]);

      Result := TActionSchemaResponse.Create;
      Result.action_name := Q.FieldByName('action_name').AsString;
      Result.direction := Q.FieldByName('direction').AsString;
      if Q.FieldByName('schema_id').IsNull then
        Result.schema_id := ''
      else
        Result.schema_id := Q.FieldByName('schema_id').AsString;
      SchemaText := Q.FieldByName('schema_json').AsString;
      SchemaVal := TJSONObject.ParseJSONValue(SchemaText);
      if SchemaVal = nil then
        SchemaVal := TJSONObject.Create;
      Result.schema_json := SchemaVal;
    finally
      Q.Free;
    end;
  finally
    FLock.Release;
  end;
end;

end.
