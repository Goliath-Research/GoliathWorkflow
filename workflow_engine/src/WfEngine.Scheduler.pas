unit WfEngine.Scheduler;

{
  Delphi workflow engine runtime (single-service).
  Generates READY tasks and advances control flow; does not call SQL wf_engine_activate.

  Execution model:
  1) StartInstance transitions workflow_instance to RUNNING, initializes instance scope
     from context_json, and activates root node via control flow.
  2) Action nodes become READY and are claimed by workers through worker API procedures.
  3) ProcessWorkerSubmit/OnTaskCompleted commits action results and lets control flow
     continue the parent composite until the instance reaches COMPLETED or FAILED.
  4) RunSchedulerTick is currently observability-oriented (counts running instances and
     ready tasks); it does not perform queue generation because activation happens inline.
}

interface

uses
  System.Generics.Collections,
  System.SysUtils,
  Uni,
  WfEngine.ControlFlow,
  WfEngine.Exceptions,
  WfEngine.Interfaces,
  WfEngine.JsonResolver,
  WfEngine.Repository,
  WfEngine.Scope,
  WfEngine.Types;

type
  TWorkflowEngine = class(TInterfacedObject, IWorkflowEngine)
  private
    FConnection: TUniConnection;
    FRepository: IWorkflowRepository;
    FJsonResolver: IWorkflowJsonResolver;
    FControlFlow: IWorkflowControlFlow;
    FScope: TWorkflowScope;
    FLogger: IWfEngineLogger;
    FGraphCache: TDictionary<Int64, TWorkflowGraph>;
    function ScopeRootForExecution(const AGraph: TWorkflowGraph;
      const ARec: TNodeExecution): Int64;
    procedure LogInfo(const AMsg: string);
    procedure InternalActivateNode(const AGraph: TWorkflowGraph;
      const AContext: TActivationContext; const ANodeId: Int64);
    function GetGraph(const AVersionId: Int64): TWorkflowGraph;
  public
    constructor Create(AConnection: TUniConnection; const ALogger: IWfEngineLogger = nil);
    destructor Destroy; override;
    procedure StartInstance(const AWorkflowInstanceId: Int64);
    function RunSchedulerTick(const AMaxInstances: Integer): TSchedulerTickResult;
    procedure OnTaskCompleted(const ANodeExecutionId: Int64; AResultCode: Integer;
      const AOutputJson: string);
    function ResolveInputJson(const ANodeExecutionId: Int64): string;
    function ProcessWorkerSubmit(const ANodeExecutionId, AWorkerId: Int64;
      AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;
    property Repository: IWorkflowRepository read FRepository;
    property ControlFlow: IWorkflowControlFlow read FControlFlow;
  end;

  TNullWfLogger = class(TInterfacedObject, IWfEngineLogger)
    procedure Info(const AMessage: string);
    procedure Warn(const AMessage: string);
    procedure Error(const AMessage: string);
  end;

implementation

{ TNullWfLogger }

procedure TNullWfLogger.Info(const AMessage: string);
begin
end;

procedure TNullWfLogger.Warn(const AMessage: string);
begin
end;

procedure TNullWfLogger.Error(const AMessage: string);
begin
end;

{ TWorkflowEngine }

constructor TWorkflowEngine.Create(AConnection: TUniConnection;
  const ALogger: IWfEngineLogger);
begin
  inherited Create;
  FConnection := AConnection;
  if ALogger = nil then
    FLogger := TNullWfLogger.Create
  else
    FLogger := ALogger;
  FRepository := TWorkflowRepository.Create(FConnection);
  FJsonResolver := TWorkflowJsonResolver.Create(FRepository);
  FScope := TWorkflowScope.Create(FRepository, FJsonResolver);
  FControlFlow := TWorkflowControlFlow.Create(FRepository, FJsonResolver,
    procedure(const AGraph: TWorkflowGraph; const AContext: TActivationContext;
      const ANodeId: Int64)
    begin
      InternalActivateNode(AGraph, AContext, ANodeId);
    end, FLogger);
  FGraphCache := TDictionary<Int64, TWorkflowGraph>.Create;
end;

destructor TWorkflowEngine.Destroy;
var
  G: TWorkflowGraph;
begin
  for G in FGraphCache.Values do
    G.Clear;
  FGraphCache.Free;
  inherited;
end;

procedure TWorkflowEngine.LogInfo(const AMsg: string);
begin
  if FLogger <> nil then
    FLogger.Info(AMsg);
end;

function TWorkflowEngine.ScopeRootForExecution(const AGraph: TWorkflowGraph;
  const ARec: TNodeExecution): Int64;
var
  ParentRec: TNodeExecution;
  ParentNode: TWorkflowNode;
begin
  if not ARec.HasParentExecution then
    Exit(WF_INSTANCE_SCOPE_EXECUTION_ID);
  Result := ARec.ParentNodeExecutionId;
  if FRepository.TryGetNodeExecution(ARec.ParentNodeExecutionId, ParentRec) and
    AGraph.TryGetNode(ParentRec.WorkflowNodeId, ParentNode) and (ParentNode.NodeType = ntParallel) then
    Result := ARec.Id;
end;

function TWorkflowEngine.GetGraph(const AVersionId: Int64): TWorkflowGraph;
begin
  if not FGraphCache.TryGetValue(AVersionId, Result) then
  begin
    Result := FRepository.LoadGraph(AVersionId);
    FGraphCache.Add(AVersionId, Result);
  end;
end;

procedure TWorkflowEngine.InternalActivateNode(const AGraph: TWorkflowGraph;
  const AContext: TActivationContext; const ANodeId: Int64);
begin
  TWorkflowControlFlow(FControlFlow).ActivateNode(AGraph, AContext, ANodeId);
end;

procedure TWorkflowEngine.StartInstance(const AWorkflowInstanceId: Int64);
var
  VersionId: Int64;
  Graph: TWorkflowGraph;
  Ctx: TActivationContext;
  Status: TWorkflowInstanceStatus;
begin
  Status := FRepository.GetInstanceStatus(AWorkflowInstanceId);
  if Status = wisRunning then
    raise EWfState.Create('Workflow instance is already running.');
  VersionId := FRepository.GetInstanceVersionId(AWorkflowInstanceId);
  Graph := GetGraph(VersionId);
  if Graph.RootNodeId = 0 then
    raise EWfConfiguration.Create('Workflow version has no root_node_id.');

  FRepository.BeginTransaction;
  try
    FRepository.SetInstanceStatus(AWorkflowInstanceId, wisRunning);
    FScope.InitInstanceScope(AWorkflowInstanceId,
      FRepository.GetInstanceContextJson(AWorkflowInstanceId));
    Ctx.WorkflowInstanceId := AWorkflowInstanceId;
    Ctx.HasParentExecution := False;
    Ctx.IterationNo := 0;
    Ctx.HasSequenceIndex := False;
    Ctx.HasParallelIndex := False;
    FControlFlow.ActivateNode(Graph, Ctx, Graph.RootNodeId);
    FRepository.CommitTransaction;
    LogInfo(Format('Started workflow instance %d', [AWorkflowInstanceId]));
  except
    FRepository.RollbackTransaction;
    raise;
  end;
end;

function TWorkflowEngine.RunSchedulerTick(const AMaxInstances: Integer): TSchedulerTickResult;
var
  Instances: TArray<Int64>;
  InstId: Int64;
  ReadyCount: Integer;
begin
  FillChar(Result, SizeOf(Result), 0);
  Instances := FRepository.GetRunningInstances(AMaxInstances);
  for InstId in Instances do
  begin
    Inc(Result.InstancesProcessed);
    ReadyCount := FRepository.CountReadyTasks(InstId);
    Inc(Result.ReadyTasksCreated, ReadyCount);
    case FRepository.GetInstanceStatus(InstId) of
      wisCompleted: Inc(Result.InstancesCompleted);
      wisFailed: Inc(Result.InstancesFailed);
    end;
  end;
end;

procedure TWorkflowEngine.OnTaskCompleted(const ANodeExecutionId: Int64;
  AResultCode: Integer; const AOutputJson: string);
var
  Rec: TNodeExecution;
  Graph: TWorkflowGraph;
  VersionId: Int64;
begin
  if not FRepository.TryGetNodeExecution(ANodeExecutionId, Rec) then
    raise EWfState.Create('Unknown node execution: ' + IntToStr(ANodeExecutionId));
  VersionId := FRepository.GetInstanceVersionId(Rec.WorkflowInstanceId);
  Graph := GetGraph(VersionId);

  FRepository.BeginTransaction;
  try
    FControlFlow.OnActionCompleted(Graph, Rec, AResultCode, AOutputJson);
    FRepository.CommitTransaction;
  except
    FRepository.RollbackTransaction;
    raise;
  end;
end;

function TWorkflowEngine.ResolveInputJson(const ANodeExecutionId: Int64): string;
var
  Rec: TNodeExecution;
  Node: TWorkflowNode;
  Graph: TWorkflowGraph;
  Bindings: TArray<TPair<string, string>>;
begin
  if not FRepository.TryGetNodeExecution(ANodeExecutionId, Rec) then
    raise EWfState.Create('Unknown node execution.');
  Graph := GetGraph(FRepository.GetInstanceVersionId(Rec.WorkflowInstanceId));
  if not Graph.TryGetNode(Rec.WorkflowNodeId, Node) then
    raise EWfState.Create('Unknown workflow node.');
  Bindings := FRepository.LoadInputBindings(Node.Id);
  Result := FJsonResolver.ResolveInputForAction(Node, ANodeExecutionId,
    ScopeRootForExecution(Graph, Rec), Rec.WorkflowInstanceId, Bindings);
end;

function TWorkflowEngine.ProcessWorkerSubmit(const ANodeExecutionId, AWorkerId: Int64;
  AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;
var
  Rec: TNodeExecution;
  InstId: Int64;
begin
  if not FRepository.TryGetNodeExecution(ANodeExecutionId, Rec) then
  begin
    Result.Accepted := False;
    Result.InstanceStatus := wisFailed;
    Result.NextReadyCount := 0;
    Exit;
  end;
  if Rec.Status <> nesRunning then
  begin
    Result.Accepted := False;
    Result.InstanceStatus := FRepository.GetInstanceStatus(Rec.WorkflowInstanceId);
    Result.NextReadyCount := FRepository.CountReadyTasks(Rec.WorkflowInstanceId);
    Exit;
  end;

  OnTaskCompleted(ANodeExecutionId, AResultCode, AOutputJson);
  InstId := Rec.WorkflowInstanceId;
  Result.Accepted := True;
  Result.InstanceStatus := FRepository.GetInstanceStatus(InstId);
  Result.NextReadyCount := FRepository.CountReadyTasks(InstId);
end;

end.
