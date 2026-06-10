unit WfEngine.Interfaces;

interface

uses
  WfEngine.Types;

type
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

implementation

end.
