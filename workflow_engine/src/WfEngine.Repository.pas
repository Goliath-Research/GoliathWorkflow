unit WfEngine.Repository;

interface

uses
  System.Generics.Collections,
  System.SysUtils,
  System.Classes,
  Data.DB,
  Uni,
  WfEngine.Exceptions,
  WfEngine.Interfaces,
  WfEngine.Types;

type
  {
    SQL-backed repository for wf schema state.

    Notes:
    - Graph metadata (workflow_node/workflow_edge/templates/bindings) is loaded into
      TWorkflowGraph and indexed in memory by the engine.
    - Runtime progression is persisted in node_execution, execution_context, loop_state,
      task_lease and scope_variable.
    - Scope variables are resolved hierarchically: current scope execution id, then
      parent execution scopes, then instance scope (scope_node_execution_id = 0).
  }
  TWorkflowRepository = class(TInterfacedObject, IWorkflowRepository)
  private
    FConnection: TUniConnection;
    FInTransaction: Boolean;
    function OpenQuery(const ASql: string): TUniQuery;
    function ScalarInt64(const ASql: string): Int64;
    function ScalarInt(const ASql: string): Integer;
    function ScalarStr(const ASql: string): string;
    procedure ExecSql(const ASql: string);
    function ExtractJsonFragment(const AJson, AJsonPath: string; out AFragmentJson: string): Boolean;
    function TryGetScopeVariableDirect(const AInstanceId, AScopeExecId: Int64; const AVarName: string;
      out AValueJson: string): Boolean;
  public
    constructor Create(AConnection: TUniConnection);
    function LoadGraph(const AVersionId: Int64): TWorkflowGraph;
    function GetInstanceVersionId(const AInstanceId: Int64): Int64;
    function GetInstanceStatus(const AInstanceId: Int64): TWorkflowInstanceStatus;
    procedure SetInstanceStatus(const AInstanceId: Int64; AStatus: TWorkflowInstanceStatus);
    function CreateWorkflowInstance(const AVersionId: Int64; const AContextJson: string): Int64;
    function InsertNodeExecution(const ARec: TNodeExecution): Int64;
    procedure UpdateNodeExecutionStatus(const AExecutionId: Int64; AStatus: TNodeExecutionStatus;
      const AOutputJson: string; AResultCode: Integer; AHasResultCode: Boolean;
      AEngineErrorCode: Integer; const AEngineErrorMessage: string);
    procedure UpdateNodeExecutionInputJson(const AExecutionId: Int64; const AInputJson: string);
    procedure DeleteTaskLease(const ANodeExecutionId: Int64);
    procedure SaveExecutionContext(const ANodeExecutionId: Int64;
      const AEntries: TArray<TExecutionContextEntry>);
    function TryGetExecutionContextValue(const ANodeExecutionId: Int64;
      const AContextKey: string; out AValueJson: string): Boolean;
    function TryGetLatestTaskResultCode(const AInstanceId: Int64; const ANodeKey: string;
      out AResultCode: Integer): Boolean;
    function TryGetLatestTaskOutputJson(const AInstanceId: Int64; const ANodeKey: string;
      const AJsonPath: string; out AFragmentJson: string): Boolean;
    function TryGetNodeExecution(const AExecutionId: Int64; out ARec: TNodeExecution): Boolean;
    function GetChildExecutions(const AParentExecutionId: Int64): TArray<TNodeExecution>;
    function TryGetLoopState(const AScopeExecutionId: Int64; out AState: TLoopState): Boolean;
    procedure InsertLoopState(const AState: TLoopState; out AId: Int64);
    procedure UpdateLoopStateIteration(const ALoopStateId: Int64; ACurrentIteration: Integer);
    function GetRunningInstances(const AMaxCount: Integer): TArray<Int64>;
    function CountReadyTasks(const AInstanceId: Int64): Integer;
    function LoadInputBindings(const ANodeId: Int64): TArray<TPair<string, string>>;
    function GetInstanceContextJson(const AInstanceId: Int64): string;
    procedure UpdateInstanceContextJson(const AInstanceId: Int64; const AContextJson: string);
    procedure UpsertMonteCarloPlan(const AInstanceId: Int64; const ABaseProjectPath,
      ALayout: string; ASeed, AFeatureIterations, AQualityIterations: Integer;
      const AConfigJson: string);
    procedure UpsertMonteCarloRun(const AInstanceId: Int64; const ARunId: string;
      AIterationNo: Integer; const APhase, ATaskConfigJson: string);
    function TryGetMonteCarloRunTaskConfig(const AInstanceId: Int64; const ARunId: string;
      out ATaskConfigJson: string): Boolean;
    procedure DeleteScopeVariables(const AInstanceId: Int64; const AScopeExecId: Int64);
    procedure CopyScopeVariables(const AInstanceId, AFromScopeExecId, AToScopeExecId: Int64);
    procedure SetScopeVariable(const AInstanceId, AScopeExecId: Int64; const AVarName, AValueJson: string);
    function TryGetScopeVariable(const AInstanceId, AStartScopeExecId: Int64; const AVarName: string;
      out AValueJson: string): Boolean;
    function TryGetScopeVariableInt(const AInstanceId, AStartScopeExecId: Int64; const AVarName: string;
      out AValue: Integer): Boolean;
    function LoadScopeDefaults(const ANodeId: Int64): TArray<TNodeScopeDefault>;
    function LoadOutputBindings(const ANodeId: Int64): TArray<TVariableOutputBinding>;
    function TryExtractOutputFragment(const AOutputJson, AJsonPath: string; out AFragmentJson: string): Boolean;
    function ReadExecutionRow(Q: TUniQuery): TNodeExecution;
    procedure BeginTransaction;
    procedure CommitTransaction;
    procedure RollbackTransaction;
  end;

implementation

uses
  System.DateUtils,
  System.JSON,
  System.StrUtils;

{ TWorkflowRepository }

constructor TWorkflowRepository.Create(AConnection: TUniConnection);
begin
  inherited Create;
  if AConnection = nil then
    raise EWfConfiguration.Create('UniConnection is required.');
  FConnection := AConnection;
end;

function TWorkflowRepository.OpenQuery(const ASql: string): TUniQuery;
begin
  Result := TUniQuery.Create(nil);
  try
    Result.Connection := FConnection;
    Result.SQL.Text := ASql;
    Result.Open;
  except
    Result.Free;
    raise;
  end;
end;

function TWorkflowRepository.ScalarInt64(const ASql: string): Int64;
var
  Q: TUniQuery;
begin
  Q := OpenQuery(ASql);
  try
    if Q.Eof then
      Exit(0);
    if Q.Fields[0].IsNull then
      Exit(0);
    Result := Q.Fields[0].AsLargeInt;
  finally
    Q.Free;
  end;
end;

function TWorkflowRepository.ScalarInt(const ASql: string): Integer;
begin
  Result := Integer(ScalarInt64(ASql));
end;

function TWorkflowRepository.ScalarStr(const ASql: string): string;
var
  Q: TUniQuery;
begin
  Q := OpenQuery(ASql);
  try
    if Q.Eof or Q.Fields[0].IsNull then
      Exit('');
    Result := Q.Fields[0].AsString;
  finally
    Q.Free;
  end;
end;

procedure TWorkflowRepository.ExecSql(const ASql: string);
var
  Q: TUniQuery;
begin
  Q := TUniQuery.Create(nil);
  try
    Q.Connection := FConnection;
    Q.SQL.Text := ASql;
    Q.ExecSQL;
  finally
    Q.Free;
  end;
end;

procedure TWorkflowRepository.BeginTransaction;
begin
  if not FInTransaction then
  begin
    FConnection.StartTransaction;
    FInTransaction := True;
  end;
end;

procedure TWorkflowRepository.CommitTransaction;
begin
  if FInTransaction then
  begin
    FConnection.Commit;
    FInTransaction := False;
  end;
end;

procedure TWorkflowRepository.RollbackTransaction;
begin
  if FInTransaction then
  begin
    FConnection.Rollback;
    FInTransaction := False;
  end;
end;

function TWorkflowRepository.LoadGraph(const AVersionId: Int64): TWorkflowGraph;
var
  Q: TUniQuery;
  N: TWorkflowNode;
  E: TWorkflowEdge;
  Nodes: TList<TWorkflowNode>;
  Edges: TList<TWorkflowEdge>;
begin
  Result.Clear;
  Result.VersionId := AVersionId;
  Nodes := TList<TWorkflowNode>.Create;
  Edges := TList<TWorkflowEdge>.Create;
  try
    Q := OpenQuery(Format(
      'SELECT id, workflow_version_id, node_type, node_key, workflow_action_id, ' +
      'repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var ' +
      'FROM %s.workflow_node WHERE workflow_version_id = %d',
      [WF_SCHEMA, AVersionId]));
    try
      while not Q.Eof do
      begin
        N.Id := Q.FieldByName('id').AsLargeInt;
        N.WorkflowVersionId := Q.FieldByName('workflow_version_id').AsLargeInt;
        N.NodeType := TNodeType.FromDb(Q.FieldByName('node_type').AsString);
        N.NodeKey := Q.FieldByName('node_key').AsString;
        if Q.FieldByName('workflow_action_id').IsNull then
          N.HasAction := False
        else
        begin
          N.HasAction := True;
          N.WorkflowActionId := Q.FieldByName('workflow_action_id').AsLargeInt;
        end;
        if Q.FieldByName('repeat_count').IsNull then
          N.HasRepeatCount := False
        else
        begin
          N.HasRepeatCount := True;
          N.RepeatCount := Q.FieldByName('repeat_count').AsInteger;
        end;
        N.ConditionRefNodeKey := Q.FieldByName('condition_ref_node_key').AsString;
        N.SwitchRefNodeKey := Q.FieldByName('switch_ref_node_key').AsString;
        if Q.FindField('condition_var') <> nil then
          N.ConditionVar := Q.FieldByName('condition_var').AsString
        else
          N.ConditionVar := '';
        if Q.FindField('switch_var') <> nil then
          N.SwitchVar := Q.FieldByName('switch_var').AsString
        else
          N.SwitchVar := '';
        N.HasTemplate := False;
        N.TemplateJson := '{}';
        Nodes.Add(N);
        Q.Next;
      end;
    finally
      Q.Free;
    end;

    for var I := 0 to Nodes.Count - 1 do
    begin
      Q := OpenQuery(Format(
        'SELECT template_json FROM %s.workflow_input_template WHERE workflow_node_id = %d',
        [WF_SCHEMA, Nodes[I].Id]));
      try
        if not Q.Eof then
        begin
          N := Nodes[I];
          N.HasTemplate := True;
          N.TemplateJson := Q.FieldByName('template_json').AsString;
          Nodes[I] := N;
        end;
      finally
        Q.Free;
      end;
    end;

    Q := OpenQuery(Format(
      'SELECT id, parent_node_id, child_node_id, child_order, branch_kind, ' +
      'switch_case_value, is_default FROM %s.workflow_edge e ' +
      'INNER JOIN %s.workflow_node pn ON pn.id = e.parent_node_id ' +
      'WHERE pn.workflow_version_id = %d ORDER BY e.parent_node_id, e.child_order',
      [WF_SCHEMA, WF_SCHEMA, AVersionId]));
    try
      while not Q.Eof do
      begin
        E.Id := Q.FieldByName('id').AsLargeInt;
        E.ParentNodeId := Q.FieldByName('parent_node_id').AsLargeInt;
        E.ChildNodeId := Q.FieldByName('child_node_id').AsLargeInt;
        E.ChildOrder := Q.FieldByName('child_order').AsInteger;
        E.BranchKind := TBranchKind.FromDb(Q.FieldByName('branch_kind').AsString);
        if Q.FieldByName('switch_case_value').IsNull then
          E.HasSwitchCaseValue := False
        else
        begin
          E.HasSwitchCaseValue := True;
          E.SwitchCaseValue := Q.FieldByName('switch_case_value').AsInteger;
        end;
        E.IsDefault := Q.FieldByName('is_default').AsInteger <> 0;
        Edges.Add(E);
        Q.Next;
      end;
    finally
      Q.Free;
    end;

    Result.Nodes := Nodes.ToArray;
    Result.Edges := Edges.ToArray;
    Result.RootNodeId := ScalarInt64(Format(
      'SELECT root_node_id FROM %s.workflow_version WHERE id = %d',
      [WF_SCHEMA, AVersionId]));
    Result.BuildIndexes;
  finally
    Nodes.Free;
    Edges.Free;
  end;
end;

function TWorkflowRepository.GetInstanceVersionId(const AInstanceId: Int64): Int64;
begin
  Result := ScalarInt64(Format(
    'SELECT workflow_version_id FROM %s.workflow_instance WHERE id = %d',
    [WF_SCHEMA, AInstanceId]));
end;

function TWorkflowRepository.GetInstanceStatus(const AInstanceId: Int64): TWorkflowInstanceStatus;
begin
  Result := TWorkflowInstanceStatus.FromDb(ScalarStr(Format(
    'SELECT status FROM %s.workflow_instance WHERE id = %d',
    [WF_SCHEMA, AInstanceId])));
end;

procedure TWorkflowRepository.SetInstanceStatus(const AInstanceId: Int64;
  AStatus: TWorkflowInstanceStatus);
var
  Extra: string;
begin
  Extra := '';
  if AStatus in [wisCompleted, wisFailed, wisCancelled] then
    Extra := ', completed_at_utc = SYSUTCDATETIME()';
  if AStatus = wisRunning then
    Extra := ', started_at_utc = ISNULL(started_at_utc, SYSUTCDATETIME())';
  ExecSql(Format(
    'UPDATE %s.workflow_instance SET status = ''%s''%s WHERE id = %d',
    [WF_SCHEMA, AStatus.ToDb, Extra, AInstanceId]));
end;

function TWorkflowRepository.CreateWorkflowInstance(const AVersionId: Int64;
  const AContextJson: string): Int64;
var
  Q: TUniQuery;
  Ctx: string;
begin
  if AContextJson = '' then
    Ctx := 'NULL'
  else
    Ctx := QuotedStr(AContextJson);
  Q := TUniQuery.Create(nil);
  try
    Q.Connection := FConnection;
    Q.SQL.Text := Format(
      'INSERT INTO %s.workflow_instance (workflow_version_id, status, context_json) ' +
      'OUTPUT INSERTED.id VALUES (%d, ''CREATED'', %s)',
      [WF_SCHEMA, AVersionId, Ctx]);
    Q.Open;
    Result := Q.Fields[0].AsLargeInt;
  finally
    Q.Free;
  end;
end;

function TWorkflowRepository.InsertNodeExecution(const ARec: TNodeExecution): Int64;
var
  Q: TUniQuery;
  ParentSql: string;
  AvailSql: string;
begin
  if ARec.HasParentExecution then
    ParentSql := IntToStr(ARec.ParentNodeExecutionId)
  else
    ParentSql := 'NULL';
  if ARec.Status = nesReady then
    AvailSql := 'SYSUTCDATETIME()'
  else
    AvailSql := 'NULL';

  Q := TUniQuery.Create(nil);
  try
    Q.Connection := FConnection;
    Q.SQL.Text := Format(
      'INSERT INTO %s.node_execution (workflow_instance_id, workflow_node_id, status, ' +
      'attempt_no, parent_node_execution_id, iteration_no, input_json, available_at_utc, started_at_utc) ' +
      'OUTPUT INSERTED.id VALUES (%d, %d, ''%s'', %d, %s, %d, %s, %s, %s)',
      [WF_SCHEMA,
       ARec.WorkflowInstanceId,
       ARec.WorkflowNodeId,
       ARec.Status.ToDb,
       ARec.AttemptNo,
       ParentSql,
       ARec.IterationNo,
       IfThen(ARec.InputJson <> '', QuotedStr(ARec.InputJson), 'NULL'),
       AvailSql,
       IfThen(ARec.Status = nesRunning, 'SYSUTCDATETIME()', 'NULL')]);
    Q.Open;
    Result := Q.Fields[0].AsLargeInt;
  finally
    Q.Free;
  end;
end;

procedure TWorkflowRepository.UpdateNodeExecutionStatus(const AExecutionId: Int64;
  AStatus: TNodeExecutionStatus; const AOutputJson: string; AResultCode: Integer;
  AHasResultCode: Boolean; AEngineErrorCode: Integer; const AEngineErrorMessage: string);
var
  OutSql, RcSql, ErrSql: string;
begin
  if AOutputJson = '' then
    OutSql := 'NULL'
  else
    OutSql := QuotedStr(AOutputJson);
  if AHasResultCode then
    RcSql := Format(', result_code = %d', [AResultCode])
  else
    RcSql := '';
  if AEngineErrorCode <> 0 then
    ErrSql := Format(', engine_error_code = %d, engine_error_message = %s',
      [AEngineErrorCode, QuotedStr(AEngineErrorMessage)])
  else
    ErrSql := '';
  ExecSql(Format(
    'UPDATE %s.node_execution SET status = ''%s'', output_json = %s, ended_at_utc = SYSUTCDATETIME()%s%s WHERE id = %d',
    [WF_SCHEMA, AStatus.ToDb, OutSql, RcSql, ErrSql, AExecutionId]));
end;

procedure TWorkflowRepository.UpdateNodeExecutionInputJson(const AExecutionId: Int64;
  const AInputJson: string);
begin
  ExecSql(Format(
    'UPDATE %s.node_execution SET input_json = %s WHERE id = %d',
    [WF_SCHEMA, QuotedStr(AInputJson), AExecutionId]));
end;

procedure TWorkflowRepository.DeleteTaskLease(const ANodeExecutionId: Int64);
begin
  ExecSql(Format(
    'DELETE FROM %s.task_lease WHERE node_execution_id = %d',
    [WF_SCHEMA, ANodeExecutionId]));
end;

procedure TWorkflowRepository.SaveExecutionContext(const ANodeExecutionId: Int64;
  const AEntries: TArray<TExecutionContextEntry>);
var
  E: TExecutionContextEntry;
begin
  ExecSql(Format(
    'DELETE FROM %s.execution_context WHERE node_execution_id = %d',
    [WF_SCHEMA, ANodeExecutionId]));
  for E in AEntries do
    ExecSql(Format(
      'INSERT INTO %s.execution_context (node_execution_id, context_key, context_value_json) ' +
      'VALUES (%d, %s, %s)',
      [WF_SCHEMA, ANodeExecutionId, QuotedStr(E.ContextKey), QuotedStr(E.ContextValueJson)]));
end;

function TWorkflowRepository.TryGetExecutionContextValue(const ANodeExecutionId: Int64;
  const AContextKey: string; out AValueJson: string): Boolean;
begin
  AValueJson := ScalarStr(Format(
    'SELECT context_value_json FROM %s.execution_context WHERE node_execution_id = %d AND context_key = %s',
    [WF_SCHEMA, ANodeExecutionId, QuotedStr(AContextKey)]));
  Result := AValueJson <> '';
end;

function TWorkflowRepository.TryGetLatestTaskResultCode(const AInstanceId: Int64;
  const ANodeKey: string; out AResultCode: Integer): Boolean;
var
  Q: TUniQuery;
begin
  Q := OpenQuery(Format(
    'SELECT TOP 1 ne.result_code FROM %s.node_execution ne ' +
    'INNER JOIN %s.workflow_node wn ON wn.id = ne.workflow_node_id ' +
    'WHERE ne.workflow_instance_id = %d AND wn.node_key = %s AND ne.status = ''SUCCEEDED'' ' +
    'ORDER BY ne.ended_at_utc DESC, ne.id DESC',
    [WF_SCHEMA, WF_SCHEMA, AInstanceId, QuotedStr(ANodeKey)]));
  try
    Result := not Q.Eof and not Q.Fields[0].IsNull;
    if Result then
      AResultCode := Q.Fields[0].AsInteger;
  finally
    Q.Free;
  end;
end;

function TWorkflowRepository.ExtractJsonFragment(const AJson, AJsonPath: string;
  out AFragmentJson: string): Boolean;
var
  Root, Found: TJSONValue;
  Path: string;
  Segments: TArray<string>;
  I: Integer;
  Obj: TJSONObject;
  Arr: TJSONArray;
  Idx: Integer;
begin
  if AJson = '' then
    Exit(False);
  if AJsonPath = '' then
  begin
    AFragmentJson := AJson;
    Exit(True);
  end;
  Path := AJsonPath;
  if Path.StartsWith('$.') then
    Path := Copy(Path, 3, MaxInt)
  else if Path.StartsWith('$') then
    Path := Copy(Path, 2, MaxInt);
  Root := TJSONObject.ParseJSONValue(AJson);
  try
    if Root = nil then
      Exit(False);
    Found := Root;
    Segments := Path.Split(['.']);
    for I := 0 to High(Segments) do
    begin
      if Segments[I] = '' then
        Continue;
      if Found is TJSONObject then
      begin
        Obj := TJSONObject(Found);
        if not Obj.TryGetValue<TJSONValue>(Segments[I], Found) then
          Exit(False);
      end
      else if Found is TJSONArray then
      begin
        Arr := TJSONArray(Found);
        if not TryStrToInt(Segments[I], Idx) then
          Exit(False);
        if (Idx < 0) or (Idx >= Arr.Count) then
          Exit(False);
        Found := Arr.Items[Idx];
      end
      else
        Exit(False);
    end;
    AFragmentJson := Found.ToJSON;
    Result := True;
  finally
    Root.Free;
  end;
end;

function TWorkflowRepository.TryGetLatestTaskOutputJson(const AInstanceId: Int64;
  const ANodeKey, AJsonPath: string; out AFragmentJson: string): Boolean;
var
  OutJson: string;
begin
  OutJson := ScalarStr(Format(
    'SELECT TOP 1 CAST(ne.output_json AS NVARCHAR(MAX)) FROM %s.node_execution ne ' +
    'INNER JOIN %s.workflow_node wn ON wn.id = ne.workflow_node_id ' +
    'WHERE ne.workflow_instance_id = %d AND wn.node_key = %s AND ne.status = ''SUCCEEDED'' ' +
    'ORDER BY ne.ended_at_utc DESC, ne.id DESC',
    [WF_SCHEMA, WF_SCHEMA, AInstanceId, QuotedStr(ANodeKey)]));
  Result := ExtractJsonFragment(OutJson, AJsonPath, AFragmentJson);
end;

function TWorkflowRepository.TryExtractOutputFragment(const AOutputJson, AJsonPath: string;
  out AFragmentJson: string): Boolean;
begin
  Result := ExtractJsonFragment(AOutputJson, AJsonPath, AFragmentJson);
end;

function TWorkflowRepository.ReadExecutionRow(Q: TUniQuery): TNodeExecution;
begin
  Result.Id := Q.FieldByName('id').AsLargeInt;
  Result.WorkflowInstanceId := Q.FieldByName('workflow_instance_id').AsLargeInt;
  Result.WorkflowNodeId := Q.FieldByName('workflow_node_id').AsLargeInt;
  Result.Status := TNodeExecutionStatus.FromDb(Q.FieldByName('status').AsString);
  Result.AttemptNo := Q.FieldByName('attempt_no').AsInteger;
  if Q.FieldByName('parent_node_execution_id').IsNull then
    Result.HasParentExecution := False
  else
  begin
    Result.HasParentExecution := True;
    Result.ParentNodeExecutionId := Q.FieldByName('parent_node_execution_id').AsLargeInt;
  end;
  Result.IterationNo := Q.FieldByName('iteration_no').AsInteger;
  Result.InputJson := Q.FieldByName('input_json').AsString;
  Result.OutputJson := Q.FieldByName('output_json').AsString;
  if Q.FindField('result_code') <> nil then
  begin
    if Q.FieldByName('result_code').IsNull then
      Result.HasResultCode := False
    else
    begin
      Result.HasResultCode := True;
      Result.ResultCode := Q.FieldByName('result_code').AsInteger;
    end;
  end;
  if Q.FindField('node_key') <> nil then
    Result.NodeKey := Q.FieldByName('node_key').AsString;
  if Q.FindField('node_type') <> nil then
    Result.NodeType := TNodeType.FromDb(Q.FieldByName('node_type').AsString);
end;

function TWorkflowRepository.TryGetNodeExecution(const AExecutionId: Int64;
  out ARec: TNodeExecution): Boolean;
var
  Q: TUniQuery;
begin
  Q := OpenQuery(Format(
    'SELECT ne.*, wn.node_key, wn.node_type FROM %s.node_execution ne ' +
    'INNER JOIN %s.workflow_node wn ON wn.id = ne.workflow_node_id WHERE ne.id = %d',
    [WF_SCHEMA, WF_SCHEMA, AExecutionId]));
  try
    Result := not Q.Eof;
    if Result then
      ARec := ReadExecutionRow(Q);
  finally
    Q.Free;
  end;
end;

function TWorkflowRepository.GetChildExecutions(const AParentExecutionId: Int64): TArray<TNodeExecution>;
var
  Q: TUniQuery;
  L: TList<TNodeExecution>;
begin
  L := TList<TNodeExecution>.Create;
  try
    Q := OpenQuery(Format(
      'SELECT ne.*, wn.node_key, wn.node_type FROM %s.node_execution ne ' +
      'INNER JOIN %s.workflow_node wn ON wn.id = ne.workflow_node_id ' +
      'WHERE ne.parent_node_execution_id = %d ORDER BY ne.id',
      [WF_SCHEMA, WF_SCHEMA, AParentExecutionId]));
    try
      while not Q.Eof do
      begin
        L.Add(ReadExecutionRow(Q));
        Q.Next;
      end;
    finally
      Q.Free;
    end;
    Result := L.ToArray;
  finally
    L.Free;
  end;
end;

function TWorkflowRepository.TryGetLoopState(const AScopeExecutionId: Int64;
  out AState: TLoopState): Boolean;
var
  Q: TUniQuery;
begin
  Q := OpenQuery(Format(
    'SELECT id, workflow_instance_id, control_node_id, scope_node_execution_id, ' +
    'current_iteration, repeat_target_count FROM %s.loop_state WHERE scope_node_execution_id = %d',
    [WF_SCHEMA, AScopeExecutionId]));
  try
    Result := not Q.Eof;
    if not Result then
      Exit;
    AState.Id := Q.FieldByName('id').AsLargeInt;
    AState.WorkflowInstanceId := Q.FieldByName('workflow_instance_id').AsLargeInt;
    AState.ControlNodeId := Q.FieldByName('control_node_id').AsLargeInt;
    AState.ScopeNodeExecutionId := Q.FieldByName('scope_node_execution_id').AsLargeInt;
    AState.CurrentIteration := Q.FieldByName('current_iteration').AsInteger;
    AState.RepeatTargetCount := Q.FieldByName('repeat_target_count').AsInteger;
  finally
    Q.Free;
  end;
end;

procedure TWorkflowRepository.InsertLoopState(const AState: TLoopState; out AId: Int64);
var
  Q: TUniQuery;
begin
  Q := TUniQuery.Create(nil);
  try
    Q.Connection := FConnection;
    Q.SQL.Text := Format(
      'INSERT INTO %s.loop_state (workflow_instance_id, control_node_id, scope_node_execution_id, ' +
      'current_iteration, repeat_target_count) OUTPUT INSERTED.id VALUES (%d, %d, %d, %d, %d)',
      [WF_SCHEMA, AState.WorkflowInstanceId, AState.ControlNodeId, AState.ScopeNodeExecutionId,
       AState.CurrentIteration, AState.RepeatTargetCount]);
    Q.Open;
    AId := Q.Fields[0].AsLargeInt;
  finally
    Q.Free;
  end;
end;

procedure TWorkflowRepository.UpdateLoopStateIteration(const ALoopStateId: Int64;
  ACurrentIteration: Integer);
begin
  ExecSql(Format(
    'UPDATE %s.loop_state SET current_iteration = %d WHERE id = %d',
    [WF_SCHEMA, ACurrentIteration, ALoopStateId]));
end;

function TWorkflowRepository.GetRunningInstances(const AMaxCount: Integer): TArray<Int64>;
var
  Q: TUniQuery;
  L: TList<Int64>;
begin
  L := TList<Int64>.Create;
  try
    Q := OpenQuery(Format(
      'SELECT TOP (%d) id FROM %s.workflow_instance WHERE status = ''RUNNING'' ORDER BY id',
      [AMaxCount, WF_SCHEMA]));
    try
      while not Q.Eof do
      begin
        L.Add(Q.Fields[0].AsLargeInt);
        Q.Next;
      end;
    finally
      Q.Free;
    end;
    Result := L.ToArray;
  finally
    L.Free;
  end;
end;

function TWorkflowRepository.CountReadyTasks(const AInstanceId: Int64): Integer;
begin
  Result := ScalarInt(Format(
    'SELECT COUNT(*) FROM %s.node_execution WHERE workflow_instance_id = %d AND status = ''READY''',
    [WF_SCHEMA, AInstanceId]));
end;

function TWorkflowRepository.LoadInputBindings(const ANodeId: Int64): TArray<TPair<string, string>>;
var
  Q: TUniQuery;
  L: TList<TPair<string, string>>;
begin
  L := TList<TPair<string, string>>.Create;
  try
    Q := OpenQuery(Format(
      'SELECT target_json_path, source_expr FROM %s.workflow_input_binding WHERE workflow_node_id = %d ORDER BY id',
      [WF_SCHEMA, ANodeId]));
    try
      while not Q.Eof do
      begin
        L.Add(TPair<string, string>.Create(
          Q.FieldByName('target_json_path').AsString,
          Q.FieldByName('source_expr').AsString));
        Q.Next;
      end;
    finally
      Q.Free;
    end;
    Result := L.ToArray;
  finally
    L.Free;
  end;
end;

function TWorkflowRepository.GetInstanceContextJson(const AInstanceId: Int64): string;
begin
  Result := ScalarStr(Format(
    'SELECT CAST(context_json AS NVARCHAR(MAX)) FROM %s.workflow_instance WHERE id = %d',
    [WF_SCHEMA, AInstanceId]));
end;

procedure TWorkflowRepository.UpdateInstanceContextJson(const AInstanceId: Int64;
  const AContextJson: string);
begin
  ExecSql(Format(
    'UPDATE %s.workflow_instance SET context_json = %s WHERE id = %d',
    [WF_SCHEMA, IfThen(AContextJson <> '', QuotedStr(AContextJson), 'NULL'), AInstanceId]));
end;

procedure TWorkflowRepository.UpsertMonteCarloPlan(const AInstanceId: Int64;
  const ABaseProjectPath, ALayout: string; ASeed, AFeatureIterations,
  AQualityIterations: Integer; const AConfigJson: string);
begin
  ExecSql(Format(
    'IF EXISTS (SELECT 1 FROM %s.monte_carlo_plan WHERE workflow_instance_id = %d) ' +
    'UPDATE %s.monte_carlo_plan SET base_project_path = %s, layout_name = %s, seed = %d, ' +
    'feature_iterations = %d, quality_iterations = %d, config_json = %s, updated_at_utc = SYSUTCDATETIME() ' +
    'WHERE workflow_instance_id = %d ' +
    'ELSE INSERT INTO %s.monte_carlo_plan ' +
    '(workflow_instance_id, base_project_path, layout_name, seed, feature_iterations, quality_iterations, config_json) ' +
    'VALUES (%d, %s, %s, %d, %d, %d, %s)',
    [WF_SCHEMA, AInstanceId,
     WF_SCHEMA, QuotedStr(ABaseProjectPath), QuotedStr(ALayout), ASeed,
     AFeatureIterations, AQualityIterations, IfThen(AConfigJson <> '', QuotedStr(AConfigJson), 'NULL'),
     AInstanceId,
     WF_SCHEMA,
     AInstanceId, QuotedStr(ABaseProjectPath), QuotedStr(ALayout), ASeed,
     AFeatureIterations, AQualityIterations, IfThen(AConfigJson <> '', QuotedStr(AConfigJson), 'NULL')]));
end;

procedure TWorkflowRepository.UpsertMonteCarloRun(const AInstanceId: Int64;
  const ARunId: string; AIterationNo: Integer; const APhase, ATaskConfigJson: string);
begin
  ExecSql(Format(
    'IF EXISTS (SELECT 1 FROM %s.monte_carlo_run WHERE workflow_instance_id = %d AND run_id = %s) ' +
    'UPDATE %s.monte_carlo_run SET iteration_no = %d, phase_name = %s, task_config_json = %s, updated_at_utc = SYSUTCDATETIME() ' +
    'WHERE workflow_instance_id = %d AND run_id = %s ' +
    'ELSE INSERT INTO %s.monte_carlo_run ' +
    '(workflow_instance_id, run_id, iteration_no, phase_name, task_config_json) ' +
    'VALUES (%d, %s, %d, %s, %s)',
    [WF_SCHEMA, AInstanceId, QuotedStr(ARunId),
     WF_SCHEMA, AIterationNo, QuotedStr(APhase), IfThen(ATaskConfigJson <> '', QuotedStr(ATaskConfigJson), 'NULL'),
     AInstanceId, QuotedStr(ARunId),
     WF_SCHEMA,
     AInstanceId, QuotedStr(ARunId), AIterationNo, QuotedStr(APhase),
     IfThen(ATaskConfigJson <> '', QuotedStr(ATaskConfigJson), 'NULL')]));
end;

function TWorkflowRepository.TryGetMonteCarloRunTaskConfig(const AInstanceId: Int64;
  const ARunId: string; out ATaskConfigJson: string): Boolean;
begin
  ATaskConfigJson := ScalarStr(Format(
    'SELECT task_config_json FROM %s.monte_carlo_run WHERE workflow_instance_id = %d AND run_id = %s',
    [WF_SCHEMA, AInstanceId, QuotedStr(ARunId)]));
  Result := ATaskConfigJson <> '';
end;

procedure TWorkflowRepository.DeleteScopeVariables(const AInstanceId: Int64;
  const AScopeExecId: Int64);
begin
  ExecSql(Format(
    'DELETE FROM %s.scope_variable WHERE workflow_instance_id = %d AND scope_node_execution_id = %d',
    [WF_SCHEMA, AInstanceId, AScopeExecId]));
end;

procedure TWorkflowRepository.CopyScopeVariables(const AInstanceId, AFromScopeExecId,
  AToScopeExecId: Int64);
begin
  ExecSql(Format(
    'INSERT INTO %s.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json) ' +
    'SELECT workflow_instance_id, %d, var_name, value_json FROM %s.scope_variable ' +
    'WHERE workflow_instance_id = %d AND scope_node_execution_id = %d',
    [WF_SCHEMA, AToScopeExecId, WF_SCHEMA, AInstanceId, AFromScopeExecId]));
end;

procedure TWorkflowRepository.SetScopeVariable(const AInstanceId, AScopeExecId: Int64;
  const AVarName, AValueJson: string);
begin
  ExecSql(Format(
    'DELETE FROM %s.scope_variable WHERE workflow_instance_id = %d AND scope_node_execution_id = %d AND var_name = %s',
    [WF_SCHEMA, AInstanceId, AScopeExecId, QuotedStr(AVarName)]));
  ExecSql(Format(
    'INSERT INTO %s.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json) ' +
    'VALUES (%d, %d, %s, %s)',
    [WF_SCHEMA, AInstanceId, AScopeExecId, QuotedStr(AVarName), QuotedStr(AValueJson)]));
end;

function TWorkflowRepository.TryGetScopeVariableDirect(const AInstanceId, AScopeExecId: Int64;
  const AVarName: string; out AValueJson: string): Boolean;
begin
  AValueJson := ScalarStr(Format(
    'SELECT value_json FROM %s.scope_variable WHERE workflow_instance_id = %d AND ' +
    'scope_node_execution_id = %d AND var_name = %s',
    [WF_SCHEMA, AInstanceId, AScopeExecId, QuotedStr(AVarName)]));
  Result := AValueJson <> '';
end;

function TWorkflowRepository.TryGetScopeVariable(const AInstanceId, AStartScopeExecId: Int64;
  const AVarName: string; out AValueJson: string): Boolean;
var
  Cur: Int64;
  Rec: TNodeExecution;
begin
  Cur := AStartScopeExecId;
  while True do
  begin
    if TryGetScopeVariableDirect(AInstanceId, Cur, AVarName, AValueJson) then
      Exit(True);
    if Cur = WF_INSTANCE_SCOPE_EXECUTION_ID then
      Break;
    if not TryGetNodeExecution(Cur, Rec) then
      Break;
    if Rec.HasParentExecution then
      Cur := Rec.ParentNodeExecutionId
    else
      Cur := WF_INSTANCE_SCOPE_EXECUTION_ID;
  end;
  Result := False;
end;

function TWorkflowRepository.TryGetScopeVariableInt(const AInstanceId, AStartScopeExecId: Int64;
  const AVarName: string; out AValue: Integer): Boolean;
var
  ValJson: string;
  Num: Double;
begin
  if not TryGetScopeVariable(AInstanceId, AStartScopeExecId, AVarName, ValJson) then
    Exit(False);
  ValJson := Trim(ValJson);
  if ValJson = '' then
    Exit(False);
  if (ValJson[1] = '"') and (ValJson[High(ValJson)] = '"') then
    ValJson := Copy(ValJson, 2, Length(ValJson) - 2);
  if TryStrToInt(ValJson, AValue) then
    Exit(True);
  if TryStrToFloat(ValJson, Num) then
  begin
    AValue := Trunc(Num);
    Exit(True);
  end;
  Result := False;
end;

function TWorkflowRepository.LoadScopeDefaults(const ANodeId: Int64): TArray<TNodeScopeDefault>;
var
  Q: TUniQuery;
  L: TList<TNodeScopeDefault>;
  D: TNodeScopeDefault;
begin
  L := TList<TNodeScopeDefault>.Create;
  try
    Q := OpenQuery(Format(
      'SELECT var_name, default_expr FROM %s.node_scope_default WHERE workflow_node_id = %d ORDER BY id',
      [WF_SCHEMA, ANodeId]));
    try
      while not Q.Eof do
      begin
        D.VarName := Q.FieldByName('var_name').AsString;
        D.DefaultExpr := Q.FieldByName('default_expr').AsString;
        L.Add(D);
        Q.Next;
      end;
    finally
      Q.Free;
    end;
    Result := L.ToArray;
  finally
    L.Free;
  end;
end;

function TWorkflowRepository.LoadOutputBindings(const ANodeId: Int64): TArray<TVariableOutputBinding>;
var
  Q: TUniQuery;
  L: TList<TVariableOutputBinding>;
  B: TVariableOutputBinding;
begin
  L := TList<TVariableOutputBinding>.Create;
  try
    Q := OpenQuery(Format(
      'SELECT var_name, source_kind, source_json_path FROM %s.variable_output_binding ' +
      'WHERE workflow_node_id = %d ORDER BY id',
      [WF_SCHEMA, ANodeId]));
    try
      while not Q.Eof do
      begin
        B.VarName := Q.FieldByName('var_name').AsString;
        B.Source := TOutputBindingSource.FromDb(Q.FieldByName('source_kind').AsString);
        B.SourceJsonPath := Q.FieldByName('source_json_path').AsString;
        L.Add(B);
        Q.Next;
      end;
    finally
      Q.Free;
    end;
    Result := L.ToArray;
  finally
    L.Free;
  end;
end;

end.
