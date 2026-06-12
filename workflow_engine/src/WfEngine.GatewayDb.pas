unit WfEngine.GatewayDb;

{
  Database gateway helpers — all access via wf contract stored procedures/functions.
  No ad-hoc SQL in Delphi; UniDAC TUniStoredProc for MSSQL and PostgreSQL.
}

interface

uses
  System.SysUtils,
  Uni,
  WfEngine.Dialect,
  WfEngine.Types;

type
  TGatewayInstanceRow = record
    Found: Boolean;
    Id: Int64;
    WorkflowVersionId: Int64;
    Status: string;
  end;

  TGatewayDeleteDefRow = record
    DeletedInstanceCount: Integer;
    DeletedVersionCount: Integer;
  end;

  TGatewayActionRow = record
    ActionName: string;
    Capability: string;
    HasInputSchema: Boolean;
    HasOutputSchema: Boolean;
  end;

  TGatewayActionSchemaRow = record
    Found: Boolean;
    ActionName: string;
    Direction: string;
    SchemaId: string;
    SchemaJson: string;
  end;

procedure GatewayWorkerAuthenticate(AConnection: TUniConnection;
  AWorkerId: Int64; const AWorkerToken: string);

function GatewayCreateWorkflowInstance(AConnection: TUniConnection;
  AVersionId: Int64; const AContextJson: string): Int64;

procedure GatewayStartWorkflowInstance(AConnection: TUniConnection;
  AWorkflowInstanceId: Int64);

function GatewayGetWorkflowInstance(AConnection: TUniConnection;
  AInstanceId: Int64): TGatewayInstanceRow;

function GatewayDeleteWorkflowDefinition(AConnection: TUniConnection;
  const AWorkflowName: string; ADeleteInstances: Boolean): TGatewayDeleteDefRow;

function GatewayListActions(AConnection: TUniConnection): TArray<TGatewayActionRow>;

function GatewayGetActionSchema(AConnection: TUniConnection;
  const AActionName, ADirection: string): TGatewayActionSchemaRow;

function GatewayWorkerSubmitResult(AConnection: TUniConnection;
  ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
  AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;

implementation

uses
  Data.DB;

procedure GatewayWorkerAuthenticate(AConnection: TUniConnection;
  AWorkerId: Int64; const AWorkerToken: string);
var
  P: TUniStoredProc;
begin
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'wf_worker_authenticate';
    P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := AWorkerId;
    P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := AWorkerToken;
    P.ExecProc;
  finally
    P.Free;
  end;
end;

function GatewayCreateWorkflowInstance(AConnection: TUniConnection;
  AVersionId: Int64; const AContextJson: string): Int64;
var
  P: TUniStoredProc;
begin
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'wf_repo_create_workflow_instance';
    P.Params.CreateParam(ftLargeint, 'version_id', ptInput).AsLargeInt := AVersionId;
    if AContextJson = '' then
      P.Params.CreateParam(ftWideMemo, 'context_json', ptInput).Clear
    else
      P.Params.CreateParam(ftWideMemo, 'context_json', ptInput).AsString := AContextJson;
    P.Open;
    if P.Eof then
      raise Exception.Create('wf_repo_create_workflow_instance returned no id.');
    Result := P.FieldByName('id').AsLargeInt;
  finally
    P.Free;
  end;
end;

procedure GatewayStartWorkflowInstance(AConnection: TUniConnection;
  AWorkflowInstanceId: Int64);
var
  P: TUniStoredProc;
begin
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'sp_start_workflow_instance';
    P.Params.CreateParam(ftLargeint, 'workflow_instance_id', ptInput).AsLargeInt := AWorkflowInstanceId;
    P.ExecProc;
  finally
    P.Free;
  end;
end;

function GatewayGetWorkflowInstance(AConnection: TUniConnection;
  AInstanceId: Int64): TGatewayInstanceRow;
var
  P: TUniStoredProc;
begin
  FillChar(Result, SizeOf(Result), 0);
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'wf_repo_get_workflow_instance';
    P.Params.CreateParam(ftLargeint, 'instance_id', ptInput).AsLargeInt := AInstanceId;
    P.Open;
    if P.Eof then
      Exit;
    Result.Found := True;
    Result.Id := P.FieldByName('id').AsLargeInt;
    Result.WorkflowVersionId := P.FieldByName('workflow_version_id').AsLargeInt;
    Result.Status := P.FieldByName('status').AsString;
  finally
    P.Free;
  end;
end;

function GatewayDeleteWorkflowDefinition(AConnection: TUniConnection;
  const AWorkflowName: string; ADeleteInstances: Boolean): TGatewayDeleteDefRow;
var
  P: TUniStoredProc;
begin
  FillChar(Result, SizeOf(Result), 0);
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'sp_delete_workflow_def';
    P.Params.CreateParam(ftLargeint, 'workflow_def_id', ptInput).Clear;
    P.Params.CreateParam(ftWideString, 'workflow_name', ptInput).AsString := AWorkflowName;
    P.Params.CreateParam(ftBoolean, 'delete_instances', ptInput).AsBoolean := ADeleteInstances;
    P.Open;
    if P.Eof then
      Exit;
    Result.DeletedInstanceCount := P.FieldByName('deleted_instance_count').AsInteger;
    Result.DeletedVersionCount := P.FieldByName('deleted_version_count').AsInteger;
  finally
    P.Free;
  end;
end;

function GatewayListActions(AConnection: TUniConnection): TArray<TGatewayActionRow>;
var
  P: TUniStoredProc;
  Row: TGatewayActionRow;
  Items: TArray<TGatewayActionRow>;
  I: Integer;
begin
  SetLength(Items, 0);
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'wf_repo_list_actions';
    P.Open;
    while not P.Eof do
    begin
      Row.ActionName := P.FieldByName('action_name').AsString;
      if P.FieldByName('capability').IsNull then
        Row.Capability := ''
      else
        Row.Capability := P.FieldByName('capability').AsString;
      Row.HasInputSchema := P.FieldByName('has_input_schema').AsBoolean;
      Row.HasOutputSchema := P.FieldByName('has_output_schema').AsBoolean;
      I := Length(Items);
      SetLength(Items, I + 1);
      Items[I] := Row;
      P.Next;
    end;
    Result := Items;
  finally
    P.Free;
  end;
end;

function GatewayGetActionSchema(AConnection: TUniConnection;
  const AActionName, ADirection: string): TGatewayActionSchemaRow;
var
  P: TUniStoredProc;
begin
  FillChar(Result, SizeOf(Result), 0);
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'wf_repo_get_action_schema';
    P.Params.CreateParam(ftWideString, 'action_name', ptInput).AsString := AActionName;
    P.Params.CreateParam(ftWideString, 'direction', ptInput).AsString := ADirection;
    P.Open;
    if P.Eof then
      Exit;
    Result.Found := True;
    Result.ActionName := P.FieldByName('action_name').AsString;
    Result.Direction := P.FieldByName('direction').AsString;
    if P.FieldByName('schema_id').IsNull then
      Result.SchemaId := ''
    else
      Result.SchemaId := P.FieldByName('schema_id').AsString;
    Result.SchemaJson := P.FieldByName('schema_json').AsString;
  finally
    P.Free;
  end;
end;

function GatewayWorkerSubmitResult(AConnection: TUniConnection;
  ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
  AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;
var
  P: TUniStoredProc;
begin
  FillChar(Result, SizeOf(Result), 0);
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'sp_worker_submit_result';
    P.Params.CreateParam(ftLargeint, 'node_execution_id', ptInput).AsLargeInt := ANodeExecutionId;
    P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := AWorkerId;
    P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := AWorkerToken;
    P.Params.CreateParam(ftInteger, 'result_code', ptInput).AsInteger := AResultCode;
    if AOutputJson = '' then
      P.Params.CreateParam(ftWideMemo, 'output_json', ptInput).Clear
    else
      P.Params.CreateParam(ftWideMemo, 'output_json', ptInput).AsString := AOutputJson;
    P.Open;
    if not P.Eof then
    begin
      Result.Accepted := P.FieldByName('accepted').AsBoolean;
      Result.InstanceStatus := TWorkflowInstanceStatus.FromDb(P.FieldByName('instance_status').AsString);
      Result.NextReadyCount := P.FieldByName('next_ready_count').AsInteger;
    end;
  finally
    P.Free;
  end;
end;

end.
