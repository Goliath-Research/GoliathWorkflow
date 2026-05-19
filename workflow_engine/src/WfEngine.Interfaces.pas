unit WfEngine.Interfaces;

interface

uses
  System.Generics.Collections,
  System.SysUtils,
  WfEngine.Types;

type
  IWorkflowRepository = interface
    ['{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}']
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
    procedure BeginTransaction;
    procedure CommitTransaction;
    procedure RollbackTransaction;
  end;

  IWorkflowJsonResolver = interface
    ['{7409A9E3-5645-4085-BAE0-F559CDAB2B0C}']
    function ResolveTemplate(const ATemplate: string; const AScopeRootExecId: Int64;
      const AInstanceId: Int64): string;
    function ResolveInputForAction(const ANode: TWorkflowNode; const ANodeExecutionId: Int64;
      const AScopeRootExecId: Int64; const AInstanceId: Int64;
      const ABindings: TArray<TPair<string, string>>): string;
  end;

  IWorkflowControlFlow = interface
    ['{C3D4E5F6-7890-ABCD-EF12-345678901234}']
    procedure ActivateNode(const AGraph: TWorkflowGraph; const AContext: TActivationContext;
      const ANodeId: Int64);
    procedure OnActionCompleted(const AGraph: TWorkflowGraph; const AExecution: TNodeExecution;
      AResultCode: Integer; const AOutputJson: string);
  end;

  IWorkflowEngine = interface
    ['{D4E5F6A7-8901-BCDE-F123-456789012345}']
    procedure StartInstance(const AWorkflowInstanceId: Int64);
    function RunSchedulerTick(const AMaxInstances: Integer): TSchedulerTickResult;
    procedure OnTaskCompleted(const ANodeExecutionId: Int64; AResultCode: Integer;
      const AOutputJson: string);
    function ResolveInputJson(const ANodeExecutionId: Int64): string;
    function ProcessWorkerSubmit(const ANodeExecutionId, AWorkerId: Int64;
      AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;
  end;

  IWorkflowWorkerApi = interface
    ['{E5F6A7B8-9012-CDEF-1234-567890123456}']
    function RequestTask(AWorkerId: Int64; const AWorkerToken, ACapability: string;
      AMaxLeaseSeconds: Integer): TWorkerTaskClaimResult;
    function SubmitResult(const ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
      AResultCode: Integer; const AOutputJson: string): TSubmitResultAck;
    function Heartbeat(const ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
      AExtendSeconds: Integer): Integer;
    procedure FailTask(const ANodeExecutionId, AWorkerId: Int64; const AWorkerToken: string;
      AErrorCode: Integer; const AErrorMessage: string);
  end;

  IWfEngineLogger = interface
    ['{F6A7B8C9-0123-DEF0-2345-678901234567}']
    procedure Info(const AMessage: string);
    procedure Warn(const AMessage: string);
    procedure Error(const AMessage: string);
  end;

implementation

end.
