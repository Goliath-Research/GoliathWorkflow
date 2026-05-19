unit WfEngine.WorkerApiAdapter;

{
  Worker-facing adapter for wf.sp_worker_* procedures.
  Task generation and workflow progression are handled by TWorkflowEngine (Delphi).
  Use ProcessWorkerSubmit on the engine after workers complete tasks when bypassing
  SQL-side wf_engine_on_action_complete (recommended).
}

interface

uses
  System.SysUtils,
  Data.DB,
  Uni,
  WfEngine.Exceptions,
  WfEngine.Interfaces,
  WfEngine.Scheduler,
  WfEngine.Types;

type
  TWorkflowWorkerApi = class(TInterfacedObject, IWorkflowWorkerApi)
  private
    FConnection: TUniConnection;
    FEngine: IWorkflowEngine;
    procedure AuthenticateProc(AWorkerId: Int64; const AWorkerToken: string);
    function CallRequestTask(AWorkerId: Int64; const AWorkerToken, ACapability: string;
      AMaxLeaseSeconds: Integer): TWorkerTaskClaimResult;
  public
    constructor Create(AConnection: TUniConnection; const AEngine: IWorkflowEngine = nil);
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

constructor TWorkflowWorkerApi.Create(AConnection: TUniConnection;
  const AEngine: IWorkflowEngine);
begin
  inherited Create;
  FConnection := AConnection;
  FEngine := AEngine;
end;

procedure TWorkflowWorkerApi.AuthenticateProc(AWorkerId: Int64; const AWorkerToken: string);
var
  P: TUniStoredProc;
begin
  P := TUniStoredProc.Create(nil);
  try
    P.Connection := FConnection;
    P.StoredProcName := WF_SCHEMA + '.wf_worker_authenticate';
    P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := AWorkerId;
    P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := AWorkerToken;
    P.ExecProc;
  finally
    P.Free;
  end;
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
    P.StoredProcName := WF_SCHEMA + 'sp_worker_request_task';
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
var
  P: TUniStoredProc;
  OutAccepted: TParam;
begin
  FillChar(Result, SizeOf(Result), 0);
  AuthenticateProc(AWorkerId, AWorkerToken);

  if FEngine <> nil then
  begin
    var LeaseOk := False;
    var Q := TUniQuery.Create(nil);
    try
      Q.Connection := FConnection;
      Q.SQL.Text := Format(
        'SELECT 1 FROM %s.task_lease WHERE node_execution_id = :ne AND worker_id = :wid',
        [WF_SCHEMA]);
      Q.ParamByName('ne').AsLargeInt := ANodeExecutionId;
      Q.ParamByName('wid').AsLargeInt := AWorkerId;
      Q.Open;
      LeaseOk := not Q.Eof;
    finally
      Q.Free;
    end;
    if not LeaseOk then
      Exit;
    Result := FEngine.ProcessWorkerSubmit(ANodeExecutionId, AWorkerId, AResultCode, AOutputJson);
    Exit;
  end;

  P := TUniStoredProc.Create(nil);
  try
    P.Connection := FConnection;
    P.StoredProcName := WF_SCHEMA + 'sp_worker_submit_result';
    P.Params.CreateParam(ftLargeint, 'node_execution_id', ptInput).AsLargeInt := ANodeExecutionId;
    P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := AWorkerId;
    P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := AWorkerToken;
    P.Params.CreateParam(ftInteger, 'result_code', ptInput).AsInteger := AResultCode;
    if AOutputJson = '' then
      P.Params.CreateParam(ftWideMemo, 'output_json', ptInput).Clear
    else
      P.Params.CreateParam(ftWideMemo, 'output_json', ptInput).AsString := AOutputJson;
    OutAccepted := P.Params.CreateParam(ftBoolean, 'accepted', ptOutput);
    P.Params.CreateParam(ftString, 'instance_status', ptOutput);
    P.Params.CreateParam(ftInteger, 'next_ready_count', ptOutput);
    P.ExecProc;
    Result.Accepted := OutAccepted.AsBoolean;
    Result.InstanceStatus := TWorkflowInstanceStatus.FromDb(
      P.ParamByName('instance_status').AsString);
    Result.NextReadyCount := P.ParamByName('next_ready_count').AsInteger;
  finally
    P.Free;
  end;
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
    P.StoredProcName := WF_SCHEMA + 'sp_worker_heartbeat';
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
    P.StoredProcName := WF_SCHEMA + 'sp_worker_fail_task';
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
