unit WfEngine.ControlFlow;

interface

uses
  System.SysUtils,
  WfEngine.Exceptions,
  WfEngine.Interfaces,
  WfEngine.Scope,
  WfEngine.Types;

type
  TActivateNodeProc = reference to procedure(const AGraph: TWorkflowGraph;
    const AContext: TActivationContext; const ANodeId: Int64);

  {
    Core control-flow runtime.

    Responsibilities:
    - Create node_execution rows for ACTION and composite nodes.
    - Decide which child node to activate for each composite type.
    - Persist loop bookkeeping (REPEAT) and propagate completion upward.
    - Mark instance FAILED/COMPLETED when terminal conditions are reached.

    Composite behavior at a glance:
    - SEQUENCE: starts first child; then activates next child after each terminal child.
    - PARALLEL: starts all children; completes when all children are terminal and none failed.
    - IF: resolves condition to integer (non-zero = THEN, zero = ELSE).
    - SWITCH: resolves integer value and selects matching CASE or DEFAULT.
    - REPEAT: creates loop_state and re-enters BODY until target count is reached.
    - WHILE: evaluates condition before each BODY activation; exits when condition = 0.

    Scope behavior:
    - Every composite opens a scope rooted at its own execution id.
    - Parallel children receive a copied scope snapshot and write outputs into
      child-local scope roots (isolation between branches).
  }
  TWorkflowControlFlow = class(TInterfacedObject, IWorkflowControlFlow)
  private
    FRepository: IWorkflowRepository;
    FJsonResolver: IWorkflowJsonResolver;
    FScope: TWorkflowScope;
    FActivateNode: TActivateNodeProc;
    FLogger: IWfEngineLogger;
    function ScopeParentExecId(const AContext: TActivationContext): Int64;
    function ParentNodeIsParallel(const AGraph: TWorkflowGraph;
      const AContext: TActivationContext): Boolean;
    function ScopeWriteExecId(const AGraph: TWorkflowGraph;
      const AExecution: TNodeExecution): Int64;
    procedure FailInstance(const AInstanceId: Int64; const AExecutionId: Int64;
      AErrorCode: Integer; const AMessage: string);
    procedure CompleteComposite(const AGraph: TWorkflowGraph; const AExecutionId: Int64);
    procedure ContinueParent(const AGraph: TWorkflowGraph; const AParentExecution: TNodeExecution);
    procedure SequenceContinue(const AGraph: TWorkflowGraph; const ASequenceExecutionId: Int64);
    procedure ParallelContinue(const AGraph: TWorkflowGraph; const AParallelExecutionId: Int64);
    procedure RepeatContinue(const AGraph: TWorkflowGraph; const ARepeatExecutionId: Int64);
    procedure WhileContinue(const AGraph: TWorkflowGraph; const AWhileExecutionId: Int64);
    function CreateCompositeExecution(const AGraph: TWorkflowGraph; const ANode: TWorkflowNode;
      const AContext: TActivationContext): Int64;
    procedure SeedContext(const ANodeExecutionId: Int64; const AContext: TActivationContext;
      const AParentExecutionId: Int64);
    procedure SeedMonteCarloRunScope(const AContext: TActivationContext;
      const AScopeRootExecId: Int64);
    procedure ActivateAction(const AGraph: TWorkflowGraph; const ANode: TWorkflowNode;
      const AContext: TActivationContext);
  public
    constructor Create(const ARepository: IWorkflowRepository;
      const AJsonResolver: IWorkflowJsonResolver; const AActivateNode: TActivateNodeProc;
      const ALogger: IWfEngineLogger = nil);
    procedure ActivateNode(const AGraph: TWorkflowGraph; const AContext: TActivationContext;
      const ANodeId: Int64);
    procedure OnActionCompleted(const AGraph: TWorkflowGraph; const AExecution: TNodeExecution;
      AResultCode: Integer; const AOutputJson: string);
  end;

implementation

uses
  System.Generics.Collections,
  System.Math,
  System.JSON,
  System.StrUtils;

function JsonStringValue(const S: string): string;
var
  V: TJSONString;
begin
  V := TJSONString.Create(S);
  try
    Result := V.ToJSON;
  finally
    V.Free;
  end;
end;

{ TWorkflowControlFlow }

constructor TWorkflowControlFlow.Create(const ARepository: IWorkflowRepository;
  const AJsonResolver: IWorkflowJsonResolver; const AActivateNode: TActivateNodeProc;
  const ALogger: IWfEngineLogger);
begin
  inherited Create;
  FRepository := ARepository;
  FJsonResolver := AJsonResolver;
  FScope := TWorkflowScope.Create(FRepository, FJsonResolver);
  FActivateNode := AActivateNode;
  FLogger := ALogger;
end;

function TWorkflowControlFlow.ScopeParentExecId(const AContext: TActivationContext): Int64;
begin
  if AContext.HasParentExecution then
    Result := AContext.ParentNodeExecutionId
  else
    Result := WF_INSTANCE_SCOPE_EXECUTION_ID;
end;

function TWorkflowControlFlow.ScopeWriteExecId(const AGraph: TWorkflowGraph;
  const AExecution: TNodeExecution): Int64;
var
  ParentRec: TNodeExecution;
  ParentNode: TWorkflowNode;
begin
  if not AExecution.HasParentExecution then
    Exit(WF_INSTANCE_SCOPE_EXECUTION_ID);
  Result := AExecution.ParentNodeExecutionId;
  if FRepository.TryGetNodeExecution(AExecution.ParentNodeExecutionId, ParentRec) and
    AGraph.TryGetNode(ParentRec.WorkflowNodeId, ParentNode) and (ParentNode.NodeType = ntParallel) then
    Result := AExecution.Id;
end;

function TWorkflowControlFlow.ParentNodeIsParallel(const AGraph: TWorkflowGraph;
  const AContext: TActivationContext): Boolean;
var
  ParentRec: TNodeExecution;
  ParentNode: TWorkflowNode;
begin
  Result := False;
  if not AContext.HasParentExecution then
    Exit;
  if not FRepository.TryGetNodeExecution(AContext.ParentNodeExecutionId, ParentRec) then
    Exit;
  if AGraph.TryGetNode(ParentRec.WorkflowNodeId, ParentNode) then
    Result := ParentNode.NodeType = ntParallel;
end;

procedure TWorkflowControlFlow.FailInstance(const AInstanceId, AExecutionId: Int64;
  AErrorCode: Integer; const AMessage: string);
begin
  FRepository.UpdateNodeExecutionStatus(AExecutionId, nesFailed, '', 0, False,
    AErrorCode, AMessage);
  FRepository.SetInstanceStatus(AInstanceId, wisFailed);
end;

procedure TWorkflowControlFlow.SeedContext(const ANodeExecutionId: Int64;
  const AContext: TActivationContext; const AParentExecutionId: Int64);
var
  Entries: TList<TExecutionContextEntry>;
  E: TExecutionContextEntry;
  ParentRc: Integer;
  Rec: TNodeExecution;
begin
  Entries := TList<TExecutionContextEntry>.Create;
  try
    E.ContextKey := 'ctx.iterationNo';
    E.ContextValueJson := IntToStr(AContext.IterationNo);
    Entries.Add(E);
    if AContext.HasSequenceIndex then
    begin
      E.ContextKey := 'ctx.sequenceIndex';
      E.ContextValueJson := IntToStr(AContext.SequenceIndex);
      Entries.Add(E);
    end;
    if AContext.HasParallelIndex then
    begin
      E.ContextKey := 'ctx.parallelIndex';
      E.ContextValueJson := IntToStr(AContext.ParallelIndex);
      Entries.Add(E);
    end;
    if (AParentExecutionId > 0) and FRepository.TryGetNodeExecution(AParentExecutionId, Rec) then
    begin
      if Rec.HasResultCode then
        ParentRc := Rec.ResultCode
      else
        ParentRc := 0;
      E.ContextKey := 'ctx.parent.resultCode';
      E.ContextValueJson := IntToStr(ParentRc);
      Entries.Add(E);
    end;
    FRepository.SaveExecutionContext(ANodeExecutionId, Entries.ToArray);
  finally
    Entries.Free;
  end;
end;

procedure TWorkflowControlFlow.ActivateAction(const AGraph: TWorkflowGraph;
  const ANode: TWorkflowNode; const AContext: TActivationContext);
var
  Rec: TNodeExecution;
  ExecId: Int64;
  Bindings: TArray<TPair<string, string>>;
  InputJson: string;
  ScopeRoot: Int64;
begin
  Rec.WorkflowInstanceId := AContext.WorkflowInstanceId;
  Rec.WorkflowNodeId := ANode.Id;
  Rec.Status := nesReady;
  Rec.AttemptNo := 1;
  Rec.IterationNo := AContext.IterationNo;
  if AContext.HasParentExecution then
  begin
    Rec.HasParentExecution := True;
    Rec.ParentNodeExecutionId := AContext.ParentNodeExecutionId;
  end
  else
    Rec.HasParentExecution := False;
  Rec.InputJson := '';
  ExecId := FRepository.InsertNodeExecution(Rec);
  if AContext.HasParentExecution then
    SeedContext(ExecId, AContext, AContext.ParentNodeExecutionId)
  else
    SeedContext(ExecId, AContext, 0);
  ScopeRoot := ScopeParentExecId(AContext);
  if ParentNodeIsParallel(AGraph, AContext) then
  begin
    FRepository.CopyScopeVariables(AContext.WorkflowInstanceId,
      AContext.ParentNodeExecutionId, ExecId);
    ScopeRoot := ExecId;
  end;
  SeedMonteCarloRunScope(AContext, ScopeRoot);
  Bindings := FRepository.LoadInputBindings(ANode.Id);
  try
    InputJson := FJsonResolver.ResolveInputForAction(ANode, ExecId, ScopeRoot,
      AContext.WorkflowInstanceId, Bindings);
    FRepository.UpdateNodeExecutionInputJson(ExecId, InputJson);
  except
    on E: EWfJson do
    begin
      FailInstance(AContext.WorkflowInstanceId, ExecId, E.EngineErrorCode, E.Message);
      raise;
    end;
  end;
end;

procedure TWorkflowControlFlow.SeedMonteCarloRunScope(
  const AContext: TActivationContext; const AScopeRootExecId: Int64);
var
  Enabled, FeatureIterations, PhaseIter: Integer;
  PhaseName, RunId, TaskCfg: string;
begin
  if not FRepository.TryGetScopeVariableInt(AContext.WorkflowInstanceId,
    WF_INSTANCE_SCOPE_EXECUTION_ID, 'mc.enabled', Enabled) then
    Exit;
  if Enabled = 0 then
    Exit;
  if AContext.IterationNo <= 0 then
    Exit;

  if not FRepository.TryGetScopeVariableInt(AContext.WorkflowInstanceId,
    WF_INSTANCE_SCOPE_EXECUTION_ID, 'mc.featureIterations', FeatureIterations) then
    FeatureIterations := 0;

  if AContext.IterationNo <= FeatureIterations then
  begin
    PhaseName := 'feature';
    PhaseIter := AContext.IterationNo;
  end
  else
  begin
    PhaseName := 'quality';
    PhaseIter := AContext.IterationNo - FeatureIterations;
  end;

  RunId := Format('%s_run_%4.4d', [PhaseName, PhaseIter]);

  FRepository.SetScopeVariable(AContext.WorkflowInstanceId, AScopeRootExecId,
    'mc.phase', JsonStringValue(PhaseName));
  FRepository.SetScopeVariable(AContext.WorkflowInstanceId, AScopeRootExecId,
    'mc.phaseIteration', IntToStr(PhaseIter));
  FRepository.SetScopeVariable(AContext.WorkflowInstanceId, AScopeRootExecId,
    'mc.runId', JsonStringValue(RunId));

  if FRepository.TryGetMonteCarloRunTaskConfig(AContext.WorkflowInstanceId, RunId, TaskCfg) then
    FRepository.SetScopeVariable(AContext.WorkflowInstanceId, AScopeRootExecId,
      'mc.taskConfig', TaskCfg);
end;

function TWorkflowControlFlow.CreateCompositeExecution(const AGraph: TWorkflowGraph;
  const ANode: TWorkflowNode; const AContext: TActivationContext): Int64;
var
  Rec: TNodeExecution;
begin
  Rec.WorkflowInstanceId := AContext.WorkflowInstanceId;
  Rec.WorkflowNodeId := ANode.Id;
  Rec.Status := nesRunning;
  Rec.AttemptNo := 1;
  Rec.IterationNo := AContext.IterationNo;
  if AContext.HasParentExecution then
  begin
    Rec.HasParentExecution := True;
    Rec.ParentNodeExecutionId := AContext.ParentNodeExecutionId;
  end;
  Result := FRepository.InsertNodeExecution(Rec);
end;

procedure TWorkflowControlFlow.ActivateNode(const AGraph: TWorkflowGraph;
  const AContext: TActivationContext; const ANodeId: Int64);
var
  Node: TWorkflowNode;
  ChildEdges: TArray<TWorkflowEdge>;
  ChildCtx: TActivationContext;
  CompositeExecId: Int64;
  CondRc, SwitchVal: Integer;
  I: Integer;
  LoopSt: TLoopState;
  BodyId: Int64;
begin
  if not AGraph.TryGetNode(ANodeId, Node) then
    raise EWfState.Create('Unknown workflow node id: ' + IntToStr(ANodeId));

  { ACTION is a leaf: create READY execution, seed context, resolve input JSON. }
  if Node.NodeType = ntAction then
  begin
    ActivateAction(AGraph, Node, AContext);
    Exit;
  end;

  { Composite nodes are RUNNING and then dispatch to one or more children. }
  CompositeExecId := CreateCompositeExecution(AGraph, Node, AContext);
  FScope.OpenScope(AContext.WorkflowInstanceId, ScopeParentExecId(AContext), CompositeExecId, Node);
  ChildCtx := AContext;
  ChildCtx.HasParentExecution := True;
  ChildCtx.ParentNodeExecutionId := CompositeExecId;

  case Node.NodeType of
    ntSequence:
      begin
        { Execute child_order = 0 first; SequenceContinue handles the rest. }
        ChildEdges := AGraph.GetChildEdges(Node.Id);
        if Length(ChildEdges) = 0 then
        begin
          FRepository.UpdateNodeExecutionStatus(CompositeExecId, nesSucceeded, '', 0, False, 0, '');
          CompleteComposite(AGraph, CompositeExecId);
          Exit;
        end;
        ChildCtx.HasSequenceIndex := True;
        ChildCtx.SequenceIndex := ChildEdges[0].ChildOrder;
        FActivateNode(AGraph, ChildCtx, ChildEdges[0].ChildNodeId);
      end;
    ntParallel:
      begin
        { Fan out immediately; ParallelContinue performs join semantics. }
        ChildEdges := AGraph.GetChildEdges(Node.Id);
        for I := 0 to High(ChildEdges) do
        begin
          ChildCtx.HasParallelIndex := True;
          ChildCtx.ParallelIndex := I;
          FActivateNode(AGraph, ChildCtx, ChildEdges[I].ChildNodeId);
        end;
      end;
    ntIf:
      begin
        { Condition uses scoped variable or prior node result (non-zero = true). }
        CondRc := FScope.ResolveConditionInt(AGraph, Node, AContext.WorkflowInstanceId,
          ScopeParentExecId(AContext));
        ChildEdges := AGraph.GetChildEdges(Node.Id);
        BodyId := 0;
        for var E in ChildEdges do
        begin
          if (CondRc <> 0) and (E.BranchKind = bkThen) then
            BodyId := E.ChildNodeId
          else if (CondRc = 0) and (E.BranchKind = bkElse) then
            BodyId := E.ChildNodeId;
        end;
        if BodyId = 0 then
        begin
          FailInstance(AContext.WorkflowInstanceId, CompositeExecId,
            ENGINE_ERROR_MISSING_IF_BRANCH, 'Missing IF branch.');
          Exit;
        end;
        FActivateNode(AGraph, ChildCtx, BodyId);
      end;
    ntSwitch:
      begin
        { First matching CASE wins; falls back to DEFAULT. }
        SwitchVal := FScope.ResolveSwitchInt(AGraph, Node, AContext.WorkflowInstanceId,
          ScopeParentExecId(AContext));
        BodyId := 0;
        for var E in AGraph.GetChildEdges(Node.Id) do
        begin
          if (E.BranchKind = bkCase) and E.HasSwitchCaseValue and (E.SwitchCaseValue = SwitchVal) then
            BodyId := E.ChildNodeId;
        end;
        if BodyId = 0 then
          for var E in AGraph.GetChildEdges(Node.Id) do
            if E.BranchKind = bkDefault then
              BodyId := E.ChildNodeId;
        if BodyId = 0 then
        begin
          FailInstance(AContext.WorkflowInstanceId, CompositeExecId,
            ENGINE_ERROR_MISSING_SWITCH_CASE, 'Missing SWITCH case.');
          Exit;
        end;
        FActivateNode(AGraph, ChildCtx, BodyId);
      end;
    ntRepeat:
      begin
        { REPEAT starts BODY at iteration 1 and tracks progress in wf.loop_state. }
        LoopSt.WorkflowInstanceId := AContext.WorkflowInstanceId;
        LoopSt.ControlNodeId := Node.Id;
        LoopSt.ScopeNodeExecutionId := CompositeExecId;
        LoopSt.CurrentIteration := 0;
        if Node.HasRepeatCount then
          LoopSt.RepeatTargetCount := Node.RepeatCount
        else
          LoopSt.RepeatTargetCount := 1;
        FRepository.InsertLoopState(LoopSt, LoopSt.Id);
        ChildEdges := AGraph.GetChildEdges(Node.Id);
        BodyId := 0;
        for var E in ChildEdges do
          if E.BranchKind = bkBody then
            BodyId := E.ChildNodeId;
        if BodyId = 0 then
        begin
          FailInstance(AContext.WorkflowInstanceId, CompositeExecId,
            ENGINE_ERROR_MISSING_REPEAT_BODY, 'Missing REPEAT body.');
          Exit;
        end;
        ChildCtx.IterationNo := 1;
        FActivateNode(AGraph, ChildCtx, BodyId);
      end;
    ntWhile:
      begin
        { WHILE checks condition before each BODY dispatch and can finish immediately. }
        CondRc := FScope.ResolveConditionInt(AGraph, Node, AContext.WorkflowInstanceId,
          ScopeParentExecId(AContext));
        if CondRc = 0 then
        begin
          FRepository.UpdateNodeExecutionStatus(CompositeExecId, nesSucceeded, '', 0, False, 0, '');
          CompleteComposite(AGraph, CompositeExecId);
          Exit;
        end;
        ChildEdges := AGraph.GetChildEdges(Node.Id);
        BodyId := 0;
        for var E in ChildEdges do
          if E.BranchKind = bkBody then
            BodyId := E.ChildNodeId;
        if BodyId = 0 then
        begin
          FailInstance(AContext.WorkflowInstanceId, CompositeExecId,
            ENGINE_ERROR_MISSING_WHILE_BODY, 'Missing WHILE body.');
          Exit;
        end;
        ChildCtx.IterationNo := 1;
        FActivateNode(AGraph, ChildCtx, BodyId);
      end;
  end;
end;

procedure TWorkflowControlFlow.CompleteComposite(const AGraph: TWorkflowGraph;
  const AExecutionId: Int64);
var
  Rec, ParentExec: TNodeExecution;
begin
  if not FRepository.TryGetNodeExecution(AExecutionId, Rec) then
    Exit;
  if not Rec.HasParentExecution then
  begin
    FRepository.SetInstanceStatus(Rec.WorkflowInstanceId, wisCompleted);
    Exit;
  end;
  if FRepository.TryGetNodeExecution(Rec.ParentNodeExecutionId, ParentExec) then
    ContinueParent(AGraph, ParentExec);
end;

procedure TWorkflowControlFlow.SequenceContinue(const AGraph: TWorkflowGraph;
  const ASequenceExecutionId: Int64);
var
  SeqExec, LastChild: TNodeExecution;
  SeqNode: TWorkflowNode;
  ChildEdges: TArray<TWorkflowEdge>;
  NextOrder, I: Integer;
  Found: Boolean;
  Ctx: TActivationContext;
begin
  if not FRepository.TryGetNodeExecution(ASequenceExecutionId, SeqExec) then
    Exit;
  AGraph.TryGetNode(SeqExec.WorkflowNodeId, SeqNode);
  ChildEdges := AGraph.GetChildEdges(SeqNode.Id);
  LastChild := Default(TNodeExecution);
  for var C in FRepository.GetChildExecutions(ASequenceExecutionId) do
    if C.Status.IsTerminal and ((LastChild.Id = 0) or (C.Id > LastChild.Id)) then
      LastChild := C;
  if (LastChild.Id > 0) and (LastChild.Status = nesFailed) then
  begin
    FRepository.UpdateNodeExecutionStatus(ASequenceExecutionId, nesFailed, '', 0, False, 0, '');
    FRepository.SetInstanceStatus(SeqExec.WorkflowInstanceId, wisFailed);
    Exit;
  end;
  NextOrder := -1;
  for I := 0 to High(ChildEdges) do
    if ChildEdges[I].ChildNodeId = LastChild.WorkflowNodeId then
    begin
      NextOrder := ChildEdges[I].ChildOrder + 1;
      Break;
    end;
  Found := False;
  for I := 0 to High(ChildEdges) do
    if ChildEdges[I].ChildOrder = NextOrder then
    begin
      Ctx.WorkflowInstanceId := SeqExec.WorkflowInstanceId;
      Ctx.HasParentExecution := True;
      Ctx.ParentNodeExecutionId := ASequenceExecutionId;
      Ctx.IterationNo := SeqExec.IterationNo;
      Ctx.HasSequenceIndex := True;
      Ctx.SequenceIndex := NextOrder;
      FActivateNode(AGraph, Ctx, ChildEdges[I].ChildNodeId);
      Found := True;
      Break;
    end;
  if not Found then
  begin
    FRepository.UpdateNodeExecutionStatus(ASequenceExecutionId, nesSucceeded, '', 0, False, 0, '');
    CompleteComposite(AGraph, ASequenceExecutionId);
  end;
end;

procedure TWorkflowControlFlow.ParallelContinue(const AGraph: TWorkflowGraph;
  const AParallelExecutionId: Int64);
var
  ParExec, C: TNodeExecution;
  ParNode: TWorkflowNode;
  Total, Finished, Failed: Integer;
begin
  if not FRepository.TryGetNodeExecution(AParallelExecutionId, ParExec) then
    Exit;
  AGraph.TryGetNode(ParExec.WorkflowNodeId, ParNode);
  Total := Length(AGraph.GetChildEdges(ParNode.Id));
  Finished := 0;
  Failed := 0;
  for C in FRepository.GetChildExecutions(AParallelExecutionId) do
  begin
    if C.Status.IsTerminal then
      Inc(Finished);
    if C.Status = nesFailed then
      Inc(Failed);
  end;
  if Finished < Total then
    Exit;
  if Failed > 0 then
  begin
    FRepository.UpdateNodeExecutionStatus(AParallelExecutionId, nesFailed, '', 0, False, 0, '');
    FRepository.SetInstanceStatus(ParExec.WorkflowInstanceId, wisFailed);
    Exit;
  end;
  FRepository.UpdateNodeExecutionStatus(AParallelExecutionId, nesSucceeded, '', 0, False, 0, '');
  CompleteComposite(AGraph, AParallelExecutionId);
end;

procedure TWorkflowControlFlow.RepeatContinue(const AGraph: TWorkflowGraph;
  const ARepeatExecutionId: Int64);
var
  RepExec: TNodeExecution;
  RepNode: TWorkflowNode;
  Ls: TLoopState;
  BodyId: Int64;
  Ctx: TActivationContext;
begin
  if not FRepository.TryGetNodeExecution(ARepeatExecutionId, RepExec) then
    Exit;
  if not FRepository.TryGetLoopState(ARepeatExecutionId, Ls) then
  begin
    FailInstance(RepExec.WorkflowInstanceId, ARepeatExecutionId,
      ENGINE_ERROR_LOOP_STATE_MISSING, 'Loop state missing.');
    Exit;
  end;
  Inc(Ls.CurrentIteration);
  FRepository.UpdateLoopStateIteration(Ls.Id, Ls.CurrentIteration);
  if Ls.CurrentIteration >= Ls.RepeatTargetCount then
  begin
    FRepository.UpdateNodeExecutionStatus(ARepeatExecutionId, nesSucceeded, '', 0, False, 0, '');
    CompleteComposite(AGraph, ARepeatExecutionId);
    Exit;
  end;
  AGraph.TryGetNode(RepExec.WorkflowNodeId, RepNode);
  BodyId := 0;
  for var E in AGraph.GetChildEdges(RepNode.Id) do
    if E.BranchKind = bkBody then
      BodyId := E.ChildNodeId;
  Ctx.WorkflowInstanceId := RepExec.WorkflowInstanceId;
  Ctx.HasParentExecution := True;
  Ctx.ParentNodeExecutionId := ARepeatExecutionId;
  Ctx.IterationNo := Ls.CurrentIteration + 1;
  FActivateNode(AGraph, Ctx, BodyId);
end;

procedure TWorkflowControlFlow.WhileContinue(const AGraph: TWorkflowGraph;
  const AWhileExecutionId: Int64);
var
  WhExec: TNodeExecution;
  WhNode: TWorkflowNode;
  CondRc: Integer;
  BodyId: Int64;
  Ctx: TActivationContext;
  MaxIter: Integer;
begin
  if not FRepository.TryGetNodeExecution(AWhileExecutionId, WhExec) then
    Exit;
  AGraph.TryGetNode(WhExec.WorkflowNodeId, WhNode);
  CondRc := FScope.ResolveConditionInt(AGraph, WhNode, WhExec.WorkflowInstanceId, AWhileExecutionId);
  if CondRc = 0 then
  begin
    FRepository.UpdateNodeExecutionStatus(AWhileExecutionId, nesSucceeded, '', 0, False, 0, '');
    CompleteComposite(AGraph, AWhileExecutionId);
    Exit;
  end;
  BodyId := 0;
  for var E in AGraph.GetChildEdges(WhNode.Id) do
    if E.BranchKind = bkBody then
      BodyId := E.ChildNodeId;
  MaxIter := 0;
  for var C in FRepository.GetChildExecutions(AWhileExecutionId) do
    if C.WorkflowNodeId = BodyId then
      MaxIter := Max(MaxIter, C.IterationNo);
  Ctx.WorkflowInstanceId := WhExec.WorkflowInstanceId;
  Ctx.HasParentExecution := True;
  Ctx.ParentNodeExecutionId := AWhileExecutionId;
  Ctx.IterationNo := MaxIter + 1;
  FActivateNode(AGraph, Ctx, BodyId);
end;

procedure TWorkflowControlFlow.ContinueParent(const AGraph: TWorkflowGraph;
  const AParentExecution: TNodeExecution);
var
  ParentNode: TWorkflowNode;
begin
  if not AGraph.TryGetNode(AParentExecution.WorkflowNodeId, ParentNode) then
    Exit;
  {
    Parent continuation is the "join point" after a child finishes.
    Each composite decides whether to dispatch more children or mark itself done.
  }
  case ParentNode.NodeType of
    ntSequence: SequenceContinue(AGraph, AParentExecution.Id);
    ntParallel: ParallelContinue(AGraph, AParentExecution.Id);
    ntIf, ntSwitch:
      begin
        FRepository.UpdateNodeExecutionStatus(AParentExecution.Id, nesSucceeded, '', 0, False, 0, '');
        CompleteComposite(AGraph, AParentExecution.Id);
      end;
    ntRepeat: RepeatContinue(AGraph, AParentExecution.Id);
    ntWhile: WhileContinue(AGraph, AParentExecution.Id);
  else
    ;
  end;
end;

procedure TWorkflowControlFlow.OnActionCompleted(const AGraph: TWorkflowGraph;
  const AExecution: TNodeExecution; AResultCode: Integer; const AOutputJson: string);
var
  ParentRec: TNodeExecution;
  ActionNode: TWorkflowNode;
begin
  { Convention: negative worker result code means business failure. }
  if AResultCode < 0 then
  begin
    FRepository.UpdateNodeExecutionStatus(AExecution.Id, nesFailed, AOutputJson,
      AResultCode, True, AResultCode, '');
    FRepository.DeleteTaskLease(AExecution.Id);
    FRepository.SetInstanceStatus(AExecution.WorkflowInstanceId, wisFailed);
    Exit;
  end;

  FRepository.UpdateNodeExecutionStatus(AExecution.Id, nesSucceeded, AOutputJson,
    AResultCode, True, 0, '');
  FRepository.DeleteTaskLease(AExecution.Id);

  { Persist declared output bindings into the correct scope root. }
  if AGraph.TryGetNode(AExecution.WorkflowNodeId, ActionNode) then
    FScope.ApplyOutputBindings(AExecution.WorkflowInstanceId,
      ScopeWriteExecId(AGraph, AExecution), ActionNode, AResultCode, AOutputJson);

  if not AExecution.HasParentExecution then
  begin
    FRepository.SetInstanceStatus(AExecution.WorkflowInstanceId, wisCompleted);
    Exit;
  end;

  if FRepository.TryGetNodeExecution(AExecution.ParentNodeExecutionId, ParentRec) then
    ContinueParent(AGraph, ParentRec);
end;

end.
