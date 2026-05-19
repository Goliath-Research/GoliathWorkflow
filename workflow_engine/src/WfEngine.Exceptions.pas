unit WfEngine.Exceptions;

interface

uses
  System.SysUtils;

type
  EWfEngine = class(Exception);

  EWfConnection = class(EWfEngine);

  EWfSql = class(EWfEngine)
  private
    FSqlErrorNumber: Integer;
    FProcedureName: string;
  public
    constructor Create(const AMessage: string; ASqlErrorNumber: Integer;
      const AProcedureName: string); reintroduce;
    property SqlErrorNumber: Integer read FSqlErrorNumber;
    property ProcedureName: string read FProcedureName;
  end;

  EWfAuth = class(EWfEngine);

  EWfLease = class(EWfEngine);

  EWfState = class(EWfEngine);

  EWfJson = class(EWfEngine)
  private
    FEngineErrorCode: Integer;
  public
    constructor Create(const AMessage: string; AEngineErrorCode: Integer); reintroduce;
    property EngineErrorCode: Integer read FEngineErrorCode;
  end;

  EWfConfiguration = class(EWfEngine);

implementation

{ EWfSql }

constructor EWfSql.Create(const AMessage: string; ASqlErrorNumber: Integer;
  const AProcedureName: string);
begin
  inherited Create(AMessage);
  FSqlErrorNumber := ASqlErrorNumber;
  FProcedureName := AProcedureName;
end;

{ EWfJson }

constructor EWfJson.Create(const AMessage: string; AEngineErrorCode: Integer);
begin
  inherited Create(AMessage);
  FEngineErrorCode := AEngineErrorCode;
end;

end.
