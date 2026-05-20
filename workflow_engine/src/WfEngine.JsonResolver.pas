unit WfEngine.JsonResolver;

interface

uses
  System.Generics.Collections,
  System.JSON,
  System.SysUtils,
  WfEngine.Exceptions,
  WfEngine.Interfaces,
  WfEngine.Types;

type
  TWorkflowJsonResolver = class(TInterfacedObject, IWorkflowJsonResolver)
  private
    FRepository: IWorkflowRepository;
    function ResolveToken(const AToken: string; const AScopeRootExecId, AContextExecId: Int64;
      const AInstanceId: Int64): string;
    function ResolvePlaceholders(const AText: string; const AScopeRootExecId, AContextExecId: Int64;
      const AInstanceId: Int64): string;
    function JsonEscapeString(const S: string): string;
    function JsonModifyPath(const AJson: string; const APath, AFragment: string): string;
    function InjectMonteCarloTaskConfig(const AInputJson, ATaskConfigJson: string): string;
  public
    constructor Create(const ARepository: IWorkflowRepository);
    function ResolveTemplate(const ATemplate: string; const AScopeRootExecId: Int64;
      const AInstanceId: Int64): string;
    function ResolveInputForAction(const ANode: TWorkflowNode; const ANodeExecutionId: Int64;
      const AScopeRootExecId: Int64; const AInstanceId: Int64;
      const ABindings: TArray<TPair<string, string>>): string;
  end;

implementation

uses
  System.StrUtils;

{ TWorkflowJsonResolver }

constructor TWorkflowJsonResolver.Create(const ARepository: IWorkflowRepository);
begin
  inherited Create;
  FRepository := ARepository;
end;

function TWorkflowJsonResolver.JsonEscapeString(const S: string): string;
begin
  Result := '"' + TJSONString.Create(S).ToJSON + '"';
  Result := Result.Trim(['"']); // fallback simple
  Result := '"' + StringReplace(StringReplace(StringReplace(S, '\', '\\', [rfReplaceAll]),
    '"', '\"', [rfReplaceAll]), #10, '\n', [rfReplaceAll]) + '"';
end;

function TWorkflowJsonResolver.ResolveToken(const AToken: string; const AScopeRootExecId,
  AContextExecId: Int64; const AInstanceId: Int64): string;
var
  Rest, NodeKey, Tail, VarName: string;
  DotPos: Integer;
  Rc: Integer;
  Frag: string;
  Val: string;
begin
  if (Pos(' ', AToken) > 0) or (Pos('+', AToken) > 0) or (Pos('(', AToken) > 0) then
    raise EWfJson.Create('Unsupported placeholder expression.', ENGINE_ERROR_UNSUPPORTED_EXPR);

  if StartsText('ctx.task.', AToken) then
  begin
    Rest := Copy(AToken, 10, MaxInt);
    DotPos := Pos('.', Rest);
    if DotPos = 0 then
      raise EWfJson.Create('Invalid ctx.task reference.', ENGINE_ERROR_UNSUPPORTED_EXPR);
    NodeKey := Copy(Rest, 1, DotPos - 1);
    Tail := Copy(Rest, DotPos + 1, MaxInt);
    if Tail = 'resultCode' then
    begin
      if not FRepository.TryGetLatestTaskResultCode(AInstanceId, NodeKey, Rc) then
        raise EWfJson.Create('Missing task result for ' + NodeKey, ENGINE_ERROR_MISSING_CONTEXT);
      Exit(IntToStr(Rc));
    end;
    if StartsText('output.', Tail) then
    begin
      if not FRepository.TryGetLatestTaskOutputJson(AInstanceId, NodeKey,
        Copy(Tail, 8, MaxInt), Frag) then
        raise EWfJson.Create('Missing task output for ' + NodeKey, ENGINE_ERROR_MISSING_CONTEXT);
      Exit(Frag);
    end;
    raise EWfJson.Create('Unsupported ctx.task tail.', ENGINE_ERROR_UNSUPPORTED_EXPR);
  end;

  if StartsText('var.', AToken) then
  begin
    VarName := Copy(AToken, 5, MaxInt);
    if VarName = '' then
      raise EWfJson.Create('Empty scope variable name.', ENGINE_ERROR_UNSUPPORTED_EXPR);
    if FRepository.TryGetScopeVariable(AInstanceId, AScopeRootExecId, VarName, Val) then
      Exit(Val)
    else
      raise EWfJson.Create('Missing scope variable: ' + VarName, ENGINE_ERROR_MISSING_CONTEXT);
  end;

  if StartsText('ctx.', AToken) then
  begin
    if FRepository.TryGetExecutionContextValue(AContextExecId, AToken, Val) then
      Exit(Val)
    else
      raise EWfJson.Create('Missing context value for ' + AToken, ENGINE_ERROR_MISSING_CONTEXT);
  end;

  raise EWfJson.Create('Unsupported token: ' + AToken, ENGINE_ERROR_UNSUPPORTED_EXPR);
end;

function TWorkflowJsonResolver.ResolvePlaceholders(const AText: string;
  const AScopeRootExecId, AContextExecId, AInstanceId: Int64): string;
var
  S: string;
  StartPos, EndPos: Integer;
  Token, Frag: string;
begin
  S := AText;
  while Pos('${', S) > 0 do
  begin
    StartPos := Pos('${', S);
    EndPos := PosEx('}', S, StartPos + 2);
    if EndPos = 0 then
      Break;
    Token := Copy(S, StartPos + 2, EndPos - StartPos - 2);
    Frag := ResolveToken(Token, AScopeRootExecId, AContextExecId, AInstanceId);
    if Frag = '' then
      Frag := 'null';
    S := StuffString(S, StartPos, EndPos - StartPos + 1, Frag);
  end;
  Result := S;
end;

function TWorkflowJsonResolver.ResolveTemplate(const ATemplate: string;
  const AScopeRootExecId, AInstanceId: Int64): string;
begin
  Result := ResolvePlaceholders(ATemplate, AScopeRootExecId, AScopeRootExecId, AInstanceId);
end;

function TWorkflowJsonResolver.JsonModifyPath(const AJson: string; const APath,
  AFragment: string): string;
var
  Path: string;
  Obj: TJSONObject;
  FragVal: TJSONValue;
begin
  Path := APath;
  if not Path.StartsWith('$') then
    Path := '$.' + Path;
  Obj := TJSONObject.ParseJSONValue(AJson) as TJSONObject;
  if Obj = nil then
    raise EWfJson.Create('Invalid JSON document.', ENGINE_ERROR_INVALID_TEMPLATE_JSON);
  try
    FragVal := TJSONObject.ParseJSONValue(AFragment);
  try
    if FragVal = nil then
      FragVal := TJSONString.Create(AFragment);
    Obj.RemovePair(Copy(Path, 3, MaxInt)); // simplistic single-segment path
    Obj.AddPair(Copy(Path, 3, MaxInt), FragVal.Clone as TJSONValue);
    Result := Obj.ToJSON;
  finally
    if FragVal <> nil then
      FragVal.Free;
  end;
  finally
    Obj.Free;
  end;
end;

function TWorkflowJsonResolver.InjectMonteCarloTaskConfig(const AInputJson,
  ATaskConfigJson: string): string;
var
  Root: TJSONValue;
  TaskCfg: TJSONValue;
  Obj: TJSONObject;
  RemovedPair: TJSONPair;
begin
  if Trim(ATaskConfigJson) = '' then
    Exit(AInputJson);
  if Trim(AInputJson) = '{}' then
    Exit(ATaskConfigJson);

  Root := TJSONObject.ParseJSONValue(AInputJson);
  if Root = nil then
    raise EWfJson.Create('Invalid input JSON before MC task injection.',
      ENGINE_ERROR_INVALID_TEMPLATE_JSON);
  try
    if not (Root is TJSONObject) then
      Exit(AInputJson);
    Obj := TJSONObject(Root);
    TaskCfg := TJSONObject.ParseJSONValue(ATaskConfigJson);
    try
      if TaskCfg = nil then
        TaskCfg := TJSONString.Create(ATaskConfigJson);
      RemovedPair := Obj.RemovePair('mcTaskConfig');
      RemovedPair.Free;
      Obj.AddPair('mcTaskConfig', TaskCfg.Clone as TJSONValue);
      Result := Obj.ToJSON;
    finally
      TaskCfg.Free;
    end;
  finally
    Root.Free;
  end;
end;

function TWorkflowJsonResolver.ResolveInputForAction(const ANode: TWorkflowNode;
  const ANodeExecutionId, AScopeRootExecId, AInstanceId: Int64;
  const ABindings: TArray<TPair<string, string>>): string;
var
  Cur: string;
  Pair: TPair<string, string>;
  Frag: string;
  McTaskCfg: string;
begin
  if ANode.HasTemplate then
    Cur := ANode.TemplateJson
  else
    Cur := '{}';
  Cur := ResolvePlaceholders(Cur, AScopeRootExecId, ANodeExecutionId, AInstanceId);
  if not (Cur.Trim.StartsWith('{') or Cur.Trim.StartsWith('[')) then
    raise EWfJson.Create('Template JSON is invalid after placeholder resolution.',
      ENGINE_ERROR_INVALID_TEMPLATE_JSON);
  for Pair in ABindings do
  begin
    Frag := ResolvePlaceholders(Pair.Value, AScopeRootExecId, ANodeExecutionId, AInstanceId);
    Cur := JsonModifyPath(Cur, Pair.Key, Frag);
  end;
  if FRepository.TryGetScopeVariable(AInstanceId, AScopeRootExecId, 'mc.taskConfig', McTaskCfg) then
    Cur := InjectMonteCarloTaskConfig(Cur, McTaskCfg);
  Result := Cur;
end;

end.
