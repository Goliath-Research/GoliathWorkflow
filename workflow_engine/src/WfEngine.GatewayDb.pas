unit WfEngine.GatewayDb;

{
  Thin SQL gateway helpers — parity with workflow_engine/rest/db_client.py.
  Instance creation and activation call wf contract procs only.
}

interface

uses
  System.SysUtils,
  Uni,
  WfEngine.Dialect;

function GatewayCreateWorkflowInstance(AConnection: TUniConnection;
  const AVersionId: Int64; const AContextJson: string): Int64;

procedure GatewayStartWorkflowInstance(AConnection: TUniConnection;
  const AWorkflowInstanceId: Int64);

implementation

uses
  Data.DB;

function GatewayCreateWorkflowInstance(AConnection: TUniConnection;
  const AVersionId: Int64; const AContextJson: string): Int64;
var
  Q: TUniQuery;
begin
  Q := TUniQuery.Create(nil);
  try
    Q.Connection := AConnection;
    if GetWorkflowBackend = wbPostgres then
      Q.SQL.Text := Format(
        'SELECT id FROM %swf_repo_create_workflow_instance(:vid, CAST(:ctx AS jsonb))',
        [WfSchemaDot])
    else
      Q.SQL.Text := Format(
        'EXEC %swf_repo_create_workflow_instance @version_id = :vid, @context_json = :ctx',
        [WfSchemaDot]);
    Q.ParamByName('vid').AsLargeInt := AVersionId;
    if AContextJson = '' then
      Q.ParamByName('ctx').Clear
    else
      Q.ParamByName('ctx').AsString := AContextJson;
    Q.Open;
    Result := Q.Fields[0].AsLargeInt;
  finally
    Q.Free;
  end;
end;

procedure GatewayStartWorkflowInstance(AConnection: TUniConnection;
  const AWorkflowInstanceId: Int64);
var
  P: TUniStoredProc;
  Q: TUniQuery;
begin
  if GetWorkflowBackend = wbPostgres then
  begin
    Q := TUniQuery.Create(nil);
    try
      Q.Connection := AConnection;
      Q.SQL.Text := Format('CALL %ssp_start_workflow_instance(:id)', [WfSchemaDot]);
      Q.ParamByName('id').AsLargeInt := AWorkflowInstanceId;
      Q.ExecSQL;
    finally
      Q.Free;
    end;
    Exit;
  end;

  P := TUniStoredProc.Create(nil);
  try
    P.Connection := AConnection;
    P.StoredProcName := WfSchemaDot + 'sp_start_workflow_instance';
    P.Params.CreateParam(ftLargeint, 'workflow_instance_id', ptInput).AsLargeInt := AWorkflowInstanceId;
    P.ExecProc;
  finally
    P.Free;
  end;
end;

end.
