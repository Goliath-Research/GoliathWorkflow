unit WfEngine.WorkerApiAdapter;

{
  Worker-facing adapter for wf.sp_worker_* contract procedures.
  Workflow progression is handled in SQL (sp_worker_submit_result / wf_engine_on_action_complete).
}

interface

uses
  System.SysUtils,
  Data.DB,
  Uni,
  WfEngine.Connection,
  WfEngine.GatewayDb,
  WfEngine.Interfaces,
  WfEngine.Types;

type
  TWorkflowWorkerApi = class(TInterfacedObject, IWorkflowWorkerApi)
  private
    FConnection: TUniConnection;
    procedure AuthenticateProc(AWorkerId: Int64; const AWorkerToken: string);
    function CallRequestTask(AWorkerId: Int64; const AWorkerToken, ACapability: string;
      AMaxLeaseSeconds: Integer): TWorkerTaskClaimResult;
  public
    constructor Create(AConnection: TUniConnection);
    function RequestTask(AWorkerId: Int64; const AWorkerToken, ACapability: string;
      AMaxLeaseSeconds: Integer): TWorkerTaskClaimResult;
    function SubmitResult(const ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
      AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;
    function Heartbeat(const ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
      AExtendSeconds: Integer): Integer;
    procedure FailTask(const ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
      AErrorCode: Integer; const AErrorMessage: string);
  end;

implementation

{ TWorkflowWorkerApi }

constructor TWorkflowWorkerApi.Create(AConnection: TUniConnection);
begin
  inherited Create;
  FConnection := AConnection;
end;

procedure TWorkflowWorkerApi.AuthenticateProc(AWorkerId: Int64; const AWorkerToken: string);
begin
  GatewayWorkerAuthenticate(FConnection, AWorkerId, AWorkerToken);
end;

function TWorkflowWorkerApi.CallRequestTask(AWorkerId: Int64; const AWorkerToken,
  ACapability: string; AMaxLeaseSeconds: Integer): TWorkerTaskClaimResult;
var
  P: TUniStoredProc;
begin
  Result.HasTask := False;
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := FConnection;
    P.StoredProcName := WfSchemaDot + 'sp_worker_request_task';
    P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := AWorkerId;
    P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := AWorkerToken;
    if ACapability = '' then
      P.Params.CreateParam(ftWideString, 'capability', ptInput).Clear
    else
      P.Params.CreateParam(ftWideString, 'capability', ptInput).AsString := ACapability;
    P.Params.CreateParam(ftInteger, 'max_lease_seconds', ptInput).AsInteger := AMaxLeaseSeconds;
    P.Open;
    if P.Eof then
      Exit;
    Result.HasTask := True;
    Result.NodeExecutionId := P.FieldByName('node_execution_id').AsLargeInt;
    Result.WorkflowInstanceId := P.FieldByName('workflow_instance_id').AsLargeInt;
    Result.NodeKey := P.FieldByName('node_key').AsString;
    Result.ActionName := P.FieldByName('action_name').AsString;
    Result.Capability := P.FieldByName('capability').AsString;
    Result.AttemptNo := P.FieldByName('attempt_no').AsInteger;
    Result.InputJson := P.FieldByName('input_json').AsString;
    Result.IterationNo := P.FieldByName('iteration_no').AsInteger;
  finally
    P.Free;
  end;
end;

function TWorkflowWorkerApi.RequestTask(AWorkerId: Int64; const AWorkerToken,
  ACapability: string; AMaxLeaseSeconds: Integer): TWorkerTaskClaimResult;
begin
  AuthenticateProc(AWorkerId, AWorkerToken);
  Result := CallRequestTask(AWorkerId, AWorkerToken, ACapability, AMaxLeaseSeconds);
end;

function TWorkflowWorkerApi.SubmitResult(const ANodeExecutionId, AWorkerId: Int64;
  const AWorkerToken: string; AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;
begin
  AuthenticateProc(AWorkerId, AWorkerToken);
  Result := GatewayWorkerSubmitResult(FConnection, ANodeExecutionId, AWorkerId,
    AWorkerToken, AResultCode, AOutputJson);
end;

function TWorkflowWorkerApi.Heartbeat(const ANodeExecutionId, AWorkerId: Int64;
  const AWorkerToken: string; AExtendSeconds: Integer): Integer;
var
  P: TUniStoredProc;
begin
  AuthenticateProc(AWorkerId, AWorkerToken);
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := FConnection;
    P.StoredProcName := WfSchemaDot + 'sp_worker_heartbeat';
    P.Params.CreateParam(ftLargeint, 'node_execution_id', ptInput).AsLargeInt := ANodeExecutionId;
    P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := AWorkerId;
    P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := AWorkerToken;
    P.Params.CreateParam(ftInteger, 'extend_seconds', ptInput).AsInteger := AExtendSeconds;
    P.Open;
    if P.Eof then
      Result := 0
    else
      Result := P.Fields[0].AsInteger;
  finally
    P.Free;
  end;
end;

procedure TWorkflowWorkerApi.FailTask(const ANodeExecutionId, AWorkerId: Int64;
  const AWorkerToken: string; AErrorCode: Integer; const AErrorMessage: string);
var
  P: TUniStoredProc;
begin
  AuthenticateProc(AWorkerId, AWorkerToken);
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := FConnection;
    P.StoredProcName := WfSchemaDot + 'sp_worker_fail_task';
    P.Params.CreateParam(ftLargeint, 'node_execution_id', ptInput).AsLargeInt := ANodeExecutionId;
    P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := AWorkerId;
    P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := AWorkerToken;
    P.Params.CreateParam(ftInteger, 'error_code', ptInput).AsInteger := AErrorCode;
    P.Params.CreateParam(ftWideString, 'error_message', ptInput).AsString := AErrorMessage;
    P.ExecProc;
  finally
    P.Free;
  end;
end;

end.
