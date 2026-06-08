unit WfEngine.DbAuth;

{
  DB auth helper for the workflow engine.
  Delegates connection string and managed identity to WfEngine.Dialect.
}

interface

uses
  Uni,
  WfEngine.Dialect;

function BuildConnectionStringFromEnv: string;

function TryApplyManagedIdentityToConnection(AConn: TUniConnection; out AError: string;
  const AResource: string = ''): Boolean;

implementation

function BuildConnectionStringFromEnv: string;
begin
  Result := WfEngine.Dialect.BuildConnectionStringFromEnv;
end;

function TryApplyManagedIdentityToConnection(AConn: TUniConnection; out AError: string;
  const AResource: string): Boolean;
var
  Backend: TWorkflowBackend;
begin
  Backend := GetWorkflowBackend;
  if AResource <> '' then
  begin
    if SameText(AResource, 'https://ossrdbms-aad.database.windows.net') then
      Backend := wbPostgres
    else if SameText(AResource, 'https://database.windows.net/') then
      Backend := wbMssql;
  end;
  Result := WfEngine.Dialect.TryApplyManagedIdentityToConnection(AConn, AError, Backend);
end;

end.
