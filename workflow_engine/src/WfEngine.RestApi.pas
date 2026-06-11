unit WfEngine.RestApi;

{
  OpenAPI route handlers for contracts/openapi.yaml.
  Used by the DMVC gateway controller (WfEngine.Mvc.Controller via
  WfEngine.GatewayHost) and integration tests.
}

interface

uses
  System.SysUtils,
  System.JSON,
  Uni,
  WfEngine.Dialect,
  WfEngine.Interfaces,
  WfEngine.ServiceLoop,
  WfEngine.Types;

type
  TRestApiService = class
  private
    FSvc: TWorkflowEngineHostedService;
    FConnection: TUniConnection;
    function ParseJsonObject(const ABody: string): TJSONObject;
    function JsonGetInt64(AObj: TJSONObject; const AName: string; ARequired: Boolean;
      out AValue: Int64): Boolean;
    function JsonGetString(AObj: TJSONObject; const AName: string; ARequired: Boolean;
      out AValue: string): Boolean;
    function InstanceSummary(AInstanceId: Int64): TJSONObject;
    function MatchPath(const APath, APattern: string; out AParam: string): Boolean;
    function QueryParam(const AQuery, AName, ADefault: string): string;
  public
    constructor Create(const ASvc: TWorkflowEngineHostedService);
    function Handle(const AMethod, APath, AQuery, ABody: string; out AStatus: Integer): string;
  end;

implementation

uses
  Data.DB;

{ TRestApiService }

constructor TRestApiService.Create(const ASvc: TWorkflowEngineHostedService);
begin
  inherited Create;
  FSvc := ASvc;
  FConnection := ASvc.Connection;
end;

function TRestApiService.ParseJsonObject(const ABody: string): TJSONObject;
begin
  if Trim(ABody) = '' then
    Exit(TJSONObject.Create);
  Result := TJSONObject.ParseJSONValue(ABody) as TJSONObject;
  if Result = nil then
    raise Exception.Create('Request body must be a JSON object.');
end;

function TRestApiService.JsonGetInt64(AObj: TJSONObject; const AName: string;
  ARequired: Boolean; out AValue: Int64): Boolean;
var
  V: TJSONValue;
begin
  Result := False;
  AValue := 0;
  if AObj = nil then
  begin
    if ARequired then
      raise Exception.CreateFmt('Missing field: %s', [AName]);
    Exit(True);
  end;
  V := AObj.GetValue(AName);
  if V = nil then
  begin
    if ARequired then
      raise Exception.CreateFmt('Missing field: %s', [AName]);
    Exit(True);
  end;
  AValue := StrToInt64Def(V.Value, 0);
  Result := True;
end;

function TRestApiService.JsonGetString(AObj: TJSONObject; const AName: string;
  ARequired: Boolean; out AValue: string): Boolean;
var
  V: TJSONValue;
begin
  Result := False;
  AValue := '';
  if AObj = nil then
  begin
    if ARequired then
      raise Exception.CreateFmt('Missing field: %s', [AName]);
    Exit(True);
  end;
  V := AObj.GetValue(AName);
  if V = nil then
  begin
    if ARequired then
      raise Exception.CreateFmt('Missing field: %s', [AName]);
    Exit(True);
  end;
  AValue := V.Value;
  Result := True;
end;

function TRestApiService.MatchPath(const APath, APattern: string; out AParam: string): Boolean;
var
  Prefix, Suffix: string;
  P: Integer;
begin
  Result := False;
  AParam := '';
  P := Pos('*', APattern);
  if P = 0 then
    Exit(SameText(APath, APattern));
  Prefix := Copy(APattern, 1, P - 1);
  Suffix := Copy(APattern, P + 1, MaxInt);
  Result := APath.StartsWith(Prefix) and APath.EndsWith(Suffix) and (Length(APath) > Length(Prefix) + Length(Suffix));
  if Result then
    AParam := Copy(APath, Length(Prefix) + 1, Length(APath) - Length(Prefix) - Length(Suffix));
end;

function TRestApiService.InstanceSummary(AInstanceId: Int64): TJSONObject;
var
  Q: TUniQuery;
begin
  Result := TJSONObject.Create;
  Q := TUniQuery.Create(nil);
  try
    Q.Connection := FConnection;
    Q.SQL.Text := Format(
      'SELECT id, workflow_version_id, status FROM %sworkflow_instance WHERE id = :id',
      [WfSchemaDot]);
    Q.ParamByName('id').AsLargeInt := AInstanceId;
    Q.Open;
    if Q.Eof then
      raise Exception.CreateFmt('Instance %d not found.', [AInstanceId]);
    Result.AddPair('id', TJSONNumber.Create(Q.FieldByName('id').AsLargeInt));
    Result.AddPair('workflow_version_id', TJSONNumber.Create(Q.FieldByName('workflow_version_id').AsLargeInt));
    Result.AddPair('status', Q.FieldByName('status').AsString);
  finally
    Q.Free;
  end;
end;

function TRestApiService.QueryParam(const AQuery, AName, ADefault: string): string;
var
  P, Eq, Amp: Integer;
  Key, Rest: string;
begin
  Result := ADefault;
  Rest := AQuery;
  while Rest <> '' do
  begin
    Amp := Pos('&', Rest);
    if Amp > 0 then
    begin
      Key := Copy(Rest, 1, Amp - 1);
      Delete(Rest, 1, Amp);
    end
    else
    begin
      Key := Rest;
      Rest := '';
    end;
    Eq := Pos('=', Key);
    if Eq > 0 then
    begin
      if SameText(Copy(Key, 1, Eq - 1), AName) then
        Exit(Copy(Key, Eq + 1, MaxInt));
    end
    else if SameText(Key, AName) then
      Exit('');
  end;
end;

function TRestApiService.Handle(const AMethod, APath, AQuery, ABody: string; out AStatus: Integer): string;
var
  BodyObj: TJSONObject;
  WorkerId, NodeExecId, VersionId, InstanceId: Int64;
  WorkerToken, Capability, ErrMsg: string;
  ResultCode, ExtendSec, ErrCode: Integer;
  Claim: TWorkerTaskClaimResult;
  Ack: TSubmitResultAck;
  Resp: TJSONObject;
  RowsUpdated: Integer;
  Param: string;
  ContextJson: string;
  DeleteInstances: Boolean;
  Q: TUniQuery;
  P: TUniStoredProc;
begin
  AStatus := 404;
  Result := '{"error":"not found"}';
  BodyObj := nil;
  try
    if not FConnection.Connected then
      FConnection.Connect;

    BodyObj := ParseJsonObject(ABody);

    if SameText(AMethod, 'POST') and SameText(APath, '/v1/workers/authenticate') then
    begin
      JsonGetInt64(BodyObj, 'worker_id', True, WorkerId);
      JsonGetString(BodyObj, 'worker_token', True, WorkerToken);
      P := TUniStoredProc.Create(nil);
      try
        P.Connection := FConnection;
        P.StoredProcName := WfSchemaDot + 'wf_worker_authenticate';
        P.Params.CreateParam(ftLargeint, 'worker_id', ptInput).AsLargeInt := WorkerId;
        P.Params.CreateParam(ftWideString, 'worker_token', ptInput).AsString := WorkerToken;
        P.ExecProc;
      finally
        P.Free;
      end;
      AStatus := 200;
      Result := '{}';
      Exit;
    end;

    if SameText(AMethod, 'POST') and SameText(APath, '/v1/workers/tasks/request') then
    begin
      JsonGetInt64(BodyObj, 'worker_id', True, WorkerId);
      JsonGetString(BodyObj, 'worker_token', True, WorkerToken);
      JsonGetString(BodyObj, 'capability', False, Capability);
      var MaxLeaseVal: Int64;
      JsonGetInt64(BodyObj, 'max_lease_seconds', False, MaxLeaseVal);
      if MaxLeaseVal > 0 then ExtendSec := Integer(MaxLeaseVal) else ExtendSec := 300;
      Claim := FSvc.WorkerApi.RequestTask(WorkerId, WorkerToken, Capability, ExtendSec);
      Resp := TJSONObject.Create;
      try
        Resp.AddPair('has_task', TJSONBool.Create(Claim.HasTask));
        if Claim.HasTask then
        begin
          Resp.AddPair('node_execution_id', TJSONNumber.Create(Claim.NodeExecutionId));
          Resp.AddPair('workflow_instance_id', TJSONNumber.Create(Claim.WorkflowInstanceId));
          Resp.AddPair('node_key', Claim.NodeKey);
          Resp.AddPair('action_name', Claim.ActionName);
          Resp.AddPair('capability', Claim.Capability);
          Resp.AddPair('attempt_no', TJSONNumber.Create(Claim.AttemptNo));
          Resp.AddPair('input_json', TJSONObject.ParseJSONValue(Claim.InputJson) as TJSONValue);
          Resp.AddPair('iteration_no', TJSONNumber.Create(Claim.IterationNo));
        end;
        AStatus := 200;
        Result := Resp.ToJSON;
      finally
        Resp.Free;
      end;
      Exit;
    end;

    if SameText(AMethod, 'POST') and MatchPath(APath, '/v1/workers/tasks/*/submit', Param) then
    begin
      NodeExecId := StrToInt64Def(Param, 0);
      JsonGetInt64(BodyObj, 'worker_id', True, WorkerId);
      JsonGetString(BodyObj, 'worker_token', True, WorkerToken);
      var ResultCodeVal: Int64;
      JsonGetInt64(BodyObj, 'result_code', False, ResultCodeVal);
      ResultCode := Integer(ResultCodeVal);
      ContextJson := '';
      if BodyObj.GetValue('output_json') <> nil then
        ContextJson := BodyObj.GetValue('output_json').ToJSON;
      Ack := FSvc.WorkerApi.SubmitResult(NodeExecId, WorkerId, WorkerToken, ResultCode, ContextJson);
      Resp := TJSONObject.Create;
      try
        Resp.AddPair('accepted', TJSONBool.Create(Ack.Accepted));
        Resp.AddPair('instance_status', TWorkflowInstanceStatus.ToDb(Ack.InstanceStatus));
        Resp.AddPair('next_ready_count', TJSONNumber.Create(Ack.NextReadyCount));
        AStatus := 200;
        Result := Resp.ToJSON;
      finally
        Resp.Free;
      end;
      Exit;
    end;

    if SameText(AMethod, 'POST') and MatchPath(APath, '/v1/workers/tasks/*/heartbeat', Param) then
    begin
      NodeExecId := StrToInt64Def(Param, 0);
      JsonGetInt64(BodyObj, 'worker_id', True, WorkerId);
      JsonGetString(BodyObj, 'worker_token', True, WorkerToken);
      var ExtendVal: Int64;
      JsonGetInt64(BodyObj, 'extend_seconds', False, ExtendVal);
      if ExtendVal > 0 then ExtendSec := Integer(ExtendVal) else ExtendSec := 300;
      RowsUpdated := FSvc.WorkerApi.Heartbeat(NodeExecId, WorkerId, WorkerToken, ExtendSec);
      AStatus := 200;
      Result := Format('{"rows_updated":%d}', [RowsUpdated]);
      Exit;
    end;

    if SameText(AMethod, 'POST') and MatchPath(APath, '/v1/workers/tasks/*/fail', Param) then
    begin
      NodeExecId := StrToInt64Def(Param, 0);
      JsonGetInt64(BodyObj, 'worker_id', True, WorkerId);
      JsonGetString(BodyObj, 'worker_token', True, WorkerToken);
      var ErrCodeVal: Int64;
      JsonGetInt64(BodyObj, 'error_code', False, ErrCodeVal);
      ErrCode := Integer(ErrCodeVal);
      JsonGetString(BodyObj, 'error_message', False, ErrMsg);
      FSvc.WorkerApi.FailTask(NodeExecId, WorkerId, WorkerToken, ErrCode, ErrMsg);
      AStatus := 204;
      Result := '';
      Exit;
    end;

    if SameText(AMethod, 'GET') and SameText(APath, '/v1/actions') then
    begin
      Q := TUniQuery.Create(nil);
      Resp := TJSONObject.Create;
      try
        Q.Connection := FConnection;
        Q.SQL.Text := Format('SELECT * FROM %swf_repo_list_actions()', [WfSchemaDot]);
        Q.Open;
        var Arr := TJSONArray.Create;
        while not Q.Eof do
        begin
          var Item := TJSONObject.Create;
          Item.AddPair('action_name', Q.FieldByName('action_name').AsString);
          if Q.FieldByName('capability').IsNull then
            Item.AddPair('capability', TJSONNull.Create)
          else
            Item.AddPair('capability', Q.FieldByName('capability').AsString);
          Item.AddPair('has_input_schema', TJSONBool.Create(Q.FieldByName('has_input_schema').AsBoolean));
          Item.AddPair('has_output_schema', TJSONBool.Create(Q.FieldByName('has_output_schema').AsBoolean));
          Arr.AddElement(Item);
          Q.Next;
        end;
        Resp.AddPair('actions', Arr);
        AStatus := 200;
        Result := Resp.ToJSON;
      finally
        Q.Free;
        Resp.Free;
      end;
      Exit;
    end;

    if SameText(AMethod, 'GET') and MatchPath(APath, '/v1/actions/*/schema', Param) then
    begin
      var Direction := QueryParam(AQuery, 'direction', 'input');
      if not SameText(Direction, 'input') and not SameText(Direction, 'output') then
      begin
        AStatus := 400;
        Result := '{"error":"direction must be input or output"}';
        Exit;
      end;
      Q := TUniQuery.Create(nil);
      try
        Q.Connection := FConnection;
        if GetWorkflowBackend = wbPostgres then
          Q.SQL.Text := Format(
            'SELECT action_name, direction, schema_id, schema_json FROM %swf_repo_get_action_schema(:name, :dir)',
            [WfSchemaDot])
        else
          Q.SQL.Text := Format(
            'SELECT action_name, direction, schema_id, schema_json FROM %swf_repo_get_action_schema(:name, :dir)',
            [WfSchemaDot]);
        Q.ParamByName('name').AsString := Param;
        Q.ParamByName('dir').AsString := Direction;
        Q.Open;
        if Q.Eof then
        begin
          AStatus := 404;
          Result := Format('{"error":"schema not found for %s (%s)"}', [Param, Direction]);
          Exit;
        end;
        Resp := TJSONObject.Create;
        try
          Resp.AddPair('action_name', Q.FieldByName('action_name').AsString);
          Resp.AddPair('direction', Q.FieldByName('direction').AsString);
          if Q.FieldByName('schema_id').IsNull then
            Resp.AddPair('schema_id', TJSONNull.Create)
          else
            Resp.AddPair('schema_id', Q.FieldByName('schema_id').AsString);
          var SchemaText := Q.FieldByName('schema_json').AsString;
          var SchemaVal := TJSONObject.ParseJSONValue(SchemaText);
          if SchemaVal = nil then
            SchemaVal := TJSONObject.Create;
          Resp.AddPair('schema_json', SchemaVal);
          AStatus := 200;
          Result := Resp.ToJSON;
        finally
          Resp.Free;
        end;
      finally
        Q.Free;
      end;
      Exit;
    end;

    if SameText(AMethod, 'POST') and SameText(APath, '/v1/workflows/instances') then
    begin
      JsonGetInt64(BodyObj, 'workflow_version_id', True, VersionId);
      if BodyObj.GetValue('context_json') <> nil then
        ContextJson := BodyObj.GetValue('context_json').ToJSON
      else
        ContextJson := '{}';
      InstanceId := FSvc.CreateAndStartInstance(VersionId, ContextJson);
      Resp := InstanceSummary(InstanceId);
      try
        AStatus := 201;
        Result := Resp.ToJSON;
      finally
        Resp.Free;
      end;
      Exit;
    end;

    if SameText(AMethod, 'GET') and MatchPath(APath, '/v1/workflows/instances/*', Param) then
    begin
      InstanceId := StrToInt64Def(Param, 0);
      Resp := InstanceSummary(InstanceId);
      try
        AStatus := 200;
        Result := Resp.ToJSON;
      finally
        Resp.Free;
      end;
      Exit;
    end;

    if SameText(AMethod, 'POST') and MatchPath(APath, '/v1/workflows/instances/*/start', Param) then
    begin
      InstanceId := StrToInt64Def(Param, 0);
      FSvc.StartInstance(InstanceId);
      Resp := InstanceSummary(InstanceId);
      try
        AStatus := 200;
        Result := Resp.ToJSON;
      finally
        Resp.Free;
      end;
      Exit;
    end;

    if SameText(AMethod, 'DELETE') and MatchPath(APath, '/v1/workflows/definitions/*', Param) then
    begin
      DeleteInstances := True;
      P := TUniStoredProc.Create(nil);
      try
        P.Connection := FConnection;
        if GetWorkflowBackend = wbPostgres then
        begin
          Q := TUniQuery.Create(nil);
          try
            Q.Connection := FConnection;
            Q.SQL.Text := Format(
              'SELECT deleted_instance_count, deleted_version_count FROM %ssp_delete_workflow_def(NULL, :name, :del)',
              [WfSchemaDot]);
            Q.ParamByName('name').AsString := Param;
            Q.ParamByName('del').AsBoolean := DeleteInstances;
            Q.Open;
            AStatus := 200;
            if Q.Eof then
              Result := '{"deleted_instance_count":0,"deleted_version_count":0}'
            else
              Result := Format(
                '{"deleted_instance_count":%d,"deleted_version_count":%d}',
                [Q.FieldByName('deleted_instance_count').AsInteger,
                 Q.FieldByName('deleted_version_count').AsInteger]);
          finally
            Q.Free;
          end;
        end
        else
        begin
          P.StoredProcName := WfSchemaDot + 'sp_delete_workflow_def';
          P.Params.CreateParam(ftLargeint, 'workflow_def_id', ptInput).Clear;
          P.Params.CreateParam(ftWideString, 'workflow_name', ptInput).AsString := Param;
          P.Params.CreateParam(ftBoolean, 'delete_instances', ptInput).AsBoolean := DeleteInstances;
          P.Open;
          AStatus := 200;
          if P.Eof then
            Result := '{"deleted_instance_count":0,"deleted_version_count":0}'
          else
            Result := Format(
              '{"deleted_instance_count":%d,"deleted_version_count":%d}',
              [P.FieldByName('deleted_instance_count').AsInteger,
               P.FieldByName('deleted_version_count').AsInteger]);
        end;
      finally
        P.Free;
      end;
      Exit;
    end;
  finally
    BodyObj.Free;
  end;
end;

end.
