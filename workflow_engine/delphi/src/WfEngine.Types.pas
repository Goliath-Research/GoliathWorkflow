unit WfEngine.Types;

{
  Domain types for the Delphi workflow engine (wf schema).
  Delphi 13.x / modern RTL.
}

interface

uses
  System.Generics.Defaults,
  System.Generics.Collections,
  System.SysUtils;

type
  TWorkflowInstanceStatus = (
    wisCreated,
    wisRunning,
    wisCompleted,
    wisFailed,
    wisCancelled
  );

  TNodeExecutionStatus = (
    nesPending,
    nesReady,
    nesRunning,
    nesSucceeded,
    nesFailed,
    nesSkipped,
    nesCancelled
  );

  TNodeType = (
    ntAction,
    ntSequence,
    ntParallel,
    ntIf,
    ntSwitch,
    ntRepeat,
    ntWhile
  );

  TBranchKind = (
    bkNone,
    bkSequence,
    bkParallel,
    bkThen,
    bkElse,
    bkCase,
    bkDefault,
    bkBody
  );

  TOutputBindingSource = (
    obsResultCode,
    obsOutputPath
  );

  TWorkflowInstanceStatusHelper = record helper for TWorkflowInstanceStatus
    function ToDb: string;
    class function FromDb(const AValue: string): TWorkflowInstanceStatus; static;
  end;

  TNodeExecutionStatusHelper = record helper for TNodeExecutionStatus
    function ToDb: string;
    class function FromDb(const AValue: string): TNodeExecutionStatus; static;
    function IsTerminal: Boolean;
  end;

  TNodeTypeHelper = record helper for TNodeType
    function ToDb: string;
    class function FromDb(const AValue: string): TNodeType; static;
    function IsComposite: Boolean;
  end;

  TBranchKindHelper = record helper for TBranchKind
    function ToDb: string;
    class function FromDb(const AValue: string): TBranchKind; static;
  end;

  TOutputBindingSourceHelper = record helper for TOutputBindingSource
    function ToDb: string;
    class function FromDb(const AValue: string): TOutputBindingSource; static;
  end;

  TWorkflowEdge = record
    Id: Int64;
    ParentNodeId: Int64;
    ChildNodeId: Int64;
    ChildOrder: Integer;
    BranchKind: TBranchKind;
    SwitchCaseValue: Integer;
    HasSwitchCaseValue: Boolean;
    IsDefault: Boolean;
  end;

  TWorkflowNode = record
    Id: Int64;
    WorkflowVersionId: Int64;
    NodeType: TNodeType;
    NodeKey: string;
    WorkflowActionId: Int64;
    HasAction: Boolean;
    RepeatCount: Integer;
    HasRepeatCount: Boolean;
    ConditionRefNodeKey: string;
    SwitchRefNodeKey: string;
    ConditionVar: string;
    SwitchVar: string;
    TemplateJson: string;
    HasTemplate: Boolean;
  end;

  TVariableOutputBinding = record
    VarName: string;
    Source: TOutputBindingSource;
    SourceJsonPath: string;
  end;

  TNodeScopeDefault = record
    VarName: string;
    DefaultExpr: string;
  end;

  TScopeVariable = record
    VarName: string;
    ValueJson: string;
  end;

  TWorkflowGraph = record
    VersionId: Int64;
    RootNodeId: Int64;
    Nodes: TArray<TWorkflowNode>;
    Edges: TArray<TWorkflowEdge>;
    NodeById: TDictionary<Int64, TWorkflowNode>;
    NodeByKey: TDictionary<string, TWorkflowNode>;
    EdgesByParent: TDictionary<Int64, TList<TWorkflowEdge>>;
    procedure Clear;
    procedure BuildIndexes;
    function TryGetNode(const ANodeId: Int64; out ANode: TWorkflowNode): Boolean;
    function TryGetNodeByKey(const ANodeKey: string; out ANode: TWorkflowNode): Boolean;
    function GetChildEdges(const AParentNodeId: Int64): TArray<TWorkflowEdge>;
  end;

  TNodeExecution = record
    Id: Int64;
    WorkflowInstanceId: Int64;
    WorkflowNodeId: Int64;
    Status: TNodeExecutionStatus;
    AttemptNo: Integer;
    ParentNodeExecutionId: Int64;
    HasParentExecution: Boolean;
    IterationNo: Integer;
    InputJson: string;
    OutputJson: string;
    ResultCode: Integer;
    HasResultCode: Boolean;
    EngineErrorCode: Integer;
    EngineErrorMessage: string;
    StartedAtUtc: TDateTime;
    EndedAtUtc: TDateTime;
    AvailableAtUtc: TDateTime;
    NodeKey: string;
    NodeType: TNodeType;
  end;

  TExecutionContextEntry = record
    ContextKey: string;
    ContextValueJson: string;
  end;

  TLoopState = record
    Id: Int64;
    WorkflowInstanceId: Int64;
    ControlNodeId: Int64;
    ScopeNodeExecutionId: Int64;
    CurrentIteration: Integer;
    RepeatTargetCount: Integer;
  end;

  TActivationContext = record
    WorkflowInstanceId: Int64;
    ParentNodeExecutionId: Int64;
    HasParentExecution: Boolean;
    IterationNo: Integer;
    SequenceIndex: Integer;
    HasSequenceIndex: Boolean;
    ParallelIndex: Integer;
    HasParallelIndex: Boolean;
  end;

  TWorkerTaskClaimResult = record
    HasTask: Boolean;
    NodeExecutionId: Int64;
    WorkflowInstanceId: Int64;
    NodeKey: string;
    ActionName: string;
    Capability: string;
    AttemptNo: Integer;
    InputJson: string;
    IterationNo: Integer;
  end;

  TSubmitResultAck = record
    Accepted: Boolean;
    InstanceStatus: TWorkflowInstanceStatus;
    NextReadyCount: Integer;
  end;

  TSchedulerTickResult = record
    InstancesProcessed: Integer;
    ReadyTasksCreated: Integer;
    InstancesCompleted: Integer;
    InstancesFailed: Integer;
  end;

const
  ENGINE_ERROR_MISSING_CONTEXT = 10001;
  ENGINE_ERROR_UNSUPPORTED_EXPR = 10002;
  ENGINE_ERROR_MISSING_IF_BRANCH = 10003;
  ENGINE_ERROR_MISSING_SWITCH_CASE = 10004;
  ENGINE_ERROR_MISSING_REPEAT_BODY = 10005;
  ENGINE_ERROR_MISSING_WHILE_BODY = 10006;
  ENGINE_ERROR_LOOP_STATE_MISSING = 10007;
  ENGINE_ERROR_INVALID_TEMPLATE_JSON = 10008;

  WF_SCHEMA = 'wf';

  { Instance-level scope uses scope_node_execution_id = 0. }
  WF_INSTANCE_SCOPE_EXECUTION_ID = 0;

implementation

{ TWorkflowInstanceStatusHelper }

function TWorkflowInstanceStatusHelper.ToDb: string;
const
  MAP: array[TWorkflowInstanceStatus] of string = (
    'CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'
  );
begin
  Result := MAP[Self];
end;

class function TWorkflowInstanceStatusHelper.FromDb(const AValue: string): TWorkflowInstanceStatus;
var
  S: string;
begin
  S := UpperCase(Trim(AValue));
  if S = 'RUNNING' then Exit(wisRunning);
  if S = 'COMPLETED' then Exit(wisCompleted);
  if S = 'FAILED' then Exit(wisFailed);
  if S = 'CANCELLED' then Exit(wisCancelled);
  Result := wisCreated;
end;

{ TNodeExecutionStatusHelper }

function TNodeExecutionStatusHelper.ToDb: string;
const
  MAP: array[TNodeExecutionStatus] of string = (
    'PENDING', 'READY', 'RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED'
  );
begin
  Result := MAP[Self];
end;

class function TNodeExecutionStatusHelper.FromDb(const AValue: string): TNodeExecutionStatus;
var
  S: string;
begin
  S := UpperCase(Trim(AValue));
  if S = 'READY' then Exit(nesReady);
  if S = 'RUNNING' then Exit(nesRunning);
  if S = 'SUCCEEDED' then Exit(nesSucceeded);
  if S = 'FAILED' then Exit(nesFailed);
  if S = 'SKIPPED' then Exit(nesSkipped);
  if S = 'CANCELLED' then Exit(nesCancelled);
  Result := nesPending;
end;

function TNodeExecutionStatusHelper.IsTerminal: Boolean;
begin
  Result := Self in [nesSucceeded, nesFailed, nesSkipped, nesCancelled];
end;

{ TNodeTypeHelper }

function TNodeTypeHelper.ToDb: string;
const
  MAP: array[TNodeType] of string = (
    'ACTION', 'SEQUENCE', 'PARALLEL', 'IF', 'SWITCH', 'REPEAT', 'WHILE'
  );
begin
  Result := MAP[Self];
end;

class function TNodeTypeHelper.FromDb(const AValue: string): TNodeType;
var
  S: string;
begin
  S := UpperCase(Trim(AValue));
  if S = 'SEQUENCE' then Exit(ntSequence);
  if S = 'PARALLEL' then Exit(ntParallel);
  if S = 'IF' then Exit(ntIf);
  if S = 'SWITCH' then Exit(ntSwitch);
  if S = 'REPEAT' then Exit(ntRepeat);
  if S = 'WHILE' then Exit(ntWhile);
  Result := ntAction;
end;

function TNodeTypeHelper.IsComposite: Boolean;
begin
  Result := Self <> ntAction;
end;

{ TBranchKindHelper }

function TBranchKindHelper.ToDb: string;
const
  MAP: array[TBranchKind] of string = (
    '', 'SEQUENCE', 'PARALLEL', 'THEN', 'ELSE', 'CASE', 'DEFAULT', 'BODY'
  );
begin
  Result := MAP[Self];
end;

class function TBranchKindHelper.FromDb(const AValue: string): TBranchKind;
var
  S: string;
begin
  S := UpperCase(Trim(AValue));
  if S = '' then Exit(bkNone);
  if S = 'SEQUENCE' then Exit(bkSequence);
  if S = 'PARALLEL' then Exit(bkParallel);
  if S = 'THEN' then Exit(bkThen);
  if S = 'ELSE' then Exit(bkElse);
  if S = 'CASE' then Exit(bkCase);
  if S = 'DEFAULT' then Exit(bkDefault);
  if S = 'BODY' then Exit(bkBody);
  Result := bkNone;
end;

{ TOutputBindingSourceHelper }

function TOutputBindingSourceHelper.ToDb: string;
const
  MAP: array[TOutputBindingSource] of string = ('result_code', 'output_path');
begin
  Result := MAP[Self];
end;

class function TOutputBindingSourceHelper.FromDb(const AValue: string): TOutputBindingSource;
var
  S: string;
begin
  S := LowerCase(Trim(AValue));
  if S = 'output_path' then Exit(obsOutputPath);
  Result := obsResultCode;
end;

{ TWorkflowGraph }

procedure TWorkflowGraph.Clear;
begin
  VersionId := 0;
  RootNodeId := 0;
  SetLength(Nodes, 0);
  SetLength(Edges, 0);
  if Assigned(NodeById) then
    NodeById.Clear;
  if Assigned(NodeByKey) then
    NodeByKey.Clear;
  if Assigned(EdgesByParent) then
  begin
    for var L in EdgesByParent.Values do
      L.Free;
    EdgesByParent.Clear;
  end;
end;

procedure TWorkflowGraph.BuildIndexes;
var
  N: TWorkflowNode;
  E: TWorkflowEdge;
  L: TList<TWorkflowEdge>;
begin
  if not Assigned(NodeById) then
    NodeById := TDictionary<Int64, TWorkflowNode>.Create;
  if not Assigned(NodeByKey) then
    NodeByKey := TDictionary<string, TWorkflowNode>.Create;
  if not Assigned(EdgesByParent) then
    EdgesByParent := TDictionary<Int64, TList<TWorkflowEdge>>.Create;

  NodeById.Clear;
  NodeByKey.Clear;
  for var Pair in EdgesByParent do
    Pair.Value.Free;
  EdgesByParent.Clear;

  for N in Nodes do
  begin
    NodeById.AddOrSetValue(N.Id, N);
    NodeByKey.AddOrSetValue(LowerCase(N.NodeKey), N);
  end;

  for E in Edges do
  begin
    if not EdgesByParent.TryGetValue(E.ParentNodeId, L) then
    begin
      L := TList<TWorkflowEdge>.Create;
      EdgesByParent.Add(E.ParentNodeId, L);
    end;
    L.Add(E);
  end;

  for L in EdgesByParent.Values do
    L.Sort(
      TComparer<TWorkflowEdge>.Construct(
        function(const A, B: TWorkflowEdge): Integer
        begin
          Result := A.ChildOrder - B.ChildOrder;
        end));
end;

function TWorkflowGraph.TryGetNode(const ANodeId: Int64; out ANode: TWorkflowNode): Boolean;
begin
  Result := Assigned(NodeById) and NodeById.TryGetValue(ANodeId, ANode);
end;

function TWorkflowGraph.TryGetNodeByKey(const ANodeKey: string; out ANode: TWorkflowNode): Boolean;
begin
  Result := Assigned(NodeByKey) and NodeByKey.TryGetValue(LowerCase(ANodeKey), ANode);
end;

function TWorkflowGraph.GetChildEdges(const AParentNodeId: Int64): TArray<TWorkflowEdge>;
var
  L: TList<TWorkflowEdge>;
  I: Integer;
begin
  if not Assigned(EdgesByParent) or not EdgesByParent.TryGetValue(AParentNodeId, L) then
    Exit(nil);
  SetLength(Result, L.Count);
  for I := 0 to L.Count - 1 do
    Result[I] := L[I];
end;

end.
