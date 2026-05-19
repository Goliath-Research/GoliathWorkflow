unit WfEngine.Scope;

{
  Scoped variable resolution and scope lifecycle helpers.
}

interface

uses
  System.SysUtils,
  WfEngine.Interfaces,
  WfEngine.Types;

type
  TWorkflowScope = class
  private
    FRepository: IWorkflowRepository;
    FJsonResolver: IWorkflowJsonResolver;
  public
    constructor Create(const ARepository: IWorkflowRepository;
      const AJsonResolver: IWorkflowJsonResolver);
    procedure InitInstanceScope(const AInstanceId: Int64; const AContextJson: string);
    procedure OpenScope(const AInstanceId, AFromScopeExecId, AToScopeExecId: Int64;
      const ANode: TWorkflowNode);
    procedure ApplyOutputBindings(const AInstanceId, AScopeExecId: Int64;
      const ANode: TWorkflowNode; AResultCode: Integer; const AOutputJson: string);
    function ResolveConditionInt(const AGraph: TWorkflowGraph; const ANode: TWorkflowNode;
      const AInstanceId, AScopeReadFromExecId: Int64): Integer;
    function ResolveSwitchInt(const AGraph: TWorkflowGraph; const ANode: TWorkflowNode;
      const AInstanceId, AScopeReadFromExecId: Int64): Integer;
  end;

implementation

uses
  System.JSON,
  System.StrUtils;

{ TWorkflowScope }

constructor TWorkflowScope.Create(const ARepository: IWorkflowRepository;
  const AJsonResolver: IWorkflowJsonResolver);
begin
  inherited Create;
  FRepository := ARepository;
  FJsonResolver := AJsonResolver;
end;

procedure TWorkflowScope.InitInstanceScope(const AInstanceId: Int64; const AContextJson: string);
var
  Root: TJSONValue;
  Obj: TJSONObject;
  Pair: TJSONPair;
begin
  FRepository.DeleteScopeVariables(AInstanceId, WF_INSTANCE_SCOPE_EXECUTION_ID);
  if Trim(AContextJson) = '' then
    Exit;
  Root := TJSONObject.ParseJSONValue(AContextJson);
  if not (Root is TJSONObject) then
  begin
    Root.Free;
    Exit;
  end;
  Obj := TJSONObject(Root);
  try
    for Pair in Obj do
      FRepository.SetScopeVariable(AInstanceId, WF_INSTANCE_SCOPE_EXECUTION_ID,
        Pair.JsonString.Value, Pair.JsonValue.ToJSON);
  finally
    Obj.Free;
  end;
end;

procedure TWorkflowScope.OpenScope(const AInstanceId, AFromScopeExecId, AToScopeExecId: Int64;
  const ANode: TWorkflowNode);
var
  Def: TNodeScopeDefault;
  Resolved: string;
begin
  if AFromScopeExecId <> AToScopeExecId then
    FRepository.CopyScopeVariables(AInstanceId, AFromScopeExecId, AToScopeExecId);
  for Def in FRepository.LoadScopeDefaults(ANode.Id) do
  begin
    Resolved := FJsonResolver.ResolveTemplate(Def.DefaultExpr, AToScopeExecId, AInstanceId);
    FRepository.SetScopeVariable(AInstanceId, AToScopeExecId, Def.VarName, Resolved);
  end;
end;

procedure TWorkflowScope.ApplyOutputBindings(const AInstanceId, AScopeExecId: Int64;
  const ANode: TWorkflowNode; AResultCode: Integer; const AOutputJson: string);
var
  B: TVariableOutputBinding;
  Frag: string;
begin
  for B in FRepository.LoadOutputBindings(ANode.Id) do
  begin
    case B.Source of
      obsResultCode:
        FRepository.SetScopeVariable(AInstanceId, AScopeExecId, B.VarName, IntToStr(AResultCode));
      obsOutputPath:
        begin
          if not FRepository.TryExtractOutputFragment(AOutputJson, B.SourceJsonPath, Frag) then
            Frag := 'null';
          FRepository.SetScopeVariable(AInstanceId, AScopeExecId, B.VarName, Frag);
        end;
    end;
  end;
end;

function TWorkflowScope.ResolveConditionInt(const AGraph: TWorkflowGraph;
  const ANode: TWorkflowNode; const AInstanceId, AScopeReadFromExecId: Int64): Integer;
var
  Rc: Integer;
begin
  if Trim(ANode.ConditionVar) <> '' then
  begin
    if FRepository.TryGetScopeVariableInt(AInstanceId, AScopeReadFromExecId, ANode.ConditionVar, Result) then
      Exit;
    Result := 0;
    Exit;
  end;
  if Trim(ANode.ConditionRefNodeKey) <> '' then
  begin
    if FRepository.TryGetLatestTaskResultCode(AInstanceId, ANode.ConditionRefNodeKey, Rc) then
      Exit(Rc);
  end;
  Result := 0;
end;

function TWorkflowScope.ResolveSwitchInt(const AGraph: TWorkflowGraph; const ANode: TWorkflowNode;
  const AInstanceId, AScopeReadFromExecId: Int64): Integer;
var
  Rc: Integer;
begin
  if Trim(ANode.SwitchVar) <> '' then
  begin
    if FRepository.TryGetScopeVariableInt(AInstanceId, AScopeReadFromExecId, ANode.SwitchVar, Result) then
      Exit;
    Result := -1;
    Exit;
  end;
  if Trim(ANode.SwitchRefNodeKey) <> '' then
  begin
    if FRepository.TryGetLatestTaskResultCode(AInstanceId, ANode.SwitchRefNodeKey, Rc) then
      Exit(Rc);
  end;
  Result := -1;
end;

end.
