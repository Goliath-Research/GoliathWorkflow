unit JsonSchemaLoader;

interface

uses
  Spring.Collections,
  System.JSON,
  System.SysUtils,
  SchemaNode,
  SchemaDocument;

type
  TJsonSchemaLoader = class
  private
    FRoot: TJSONObject;
    FBaseDir: string;
    FCache: IDictionary<string, TSchemaNode>;
    FResolving: IDictionary<string, Boolean>;
    FOwned: IList<TSchemaNode>;
    FExternalRoots: IDictionary<string, TJSONObject>;
    FExternalJsonOwner: IList<TJSONValue>;
    FRefBaseStack: IList<string>;
    function NewNode: TSchemaNode;
    procedure ResetState;
    function CurrentRefBaseDir: string;
    procedure PushRefBaseDir(const Dir: string);
    procedure PopRefBaseDir;
    procedure SplitRefParts(const Ref: string; out FilePart, FragmentPart: string);
    function ResolveSchemaFilePath(const FilePart: string): string;
    function LoadExternalRoot(const AbsolutePath: string): TJSONObject;
    function NavigateFragment(Root: TJSONValue; const FragmentPart: string): TJSONValue;
    function ParseType(const TypeVal: TJSONValue): TSchemaKind;
    function IsNullSchema(const Obj: TJSONObject): Boolean;
    function TryNormalizeNullableAnyOf(const Obj: TJSONObject; out Inner: TJSONObject): Boolean;
    function ParseSchemaObject(const Obj: TJSONObject; const RefKey: string): TSchemaNode;
    procedure ApplyMetadata(const Obj: TJSONObject; Node: TSchemaNode);
    procedure ParseProperties(const Obj: TJSONObject; Node: TSchemaNode);
    procedure ParseItems(const Obj: TJSONObject; Node: TSchemaNode);
    procedure ParseAdditionalProperties(const Obj: TJSONObject; Node: TSchemaNode);
    procedure ParseOneOfDiscriminator(const Obj: TJSONObject; Node: TSchemaNode);
    function ResolveNode(const Obj: TJSONObject; const RefKey: string): TSchemaNode;
  public
    constructor Create;
    destructor Destroy; override;
    function LoadFromFile(const Path: string): TSchemaNode;
    function LoadFromString(const JsonText: string): TSchemaNode;
    function LoadFromJson(const Root: TJSONObject): TSchemaNode;
    function LoadDocumentFromFile(const Path: string): TSchemaDocument;
    function LoadDocumentFromString(const JsonText: string): TSchemaDocument;
  end;

implementation

uses
  System.Classes,
  System.IOUtils;

constructor TJsonSchemaLoader.Create;
begin
  inherited Create;
  FCache := TCollections.CreateDictionary<string, TSchemaNode>;
  FResolving := TCollections.CreateDictionary<string, Boolean>;
  FOwned := TCollections.CreateObjectList<TSchemaNode>(True);
  FExternalRoots := TCollections.CreateDictionary<string, TJSONObject>;
  FExternalJsonOwner := TCollections.CreateObjectList<TJSONValue>(True);
  FRefBaseStack := TCollections.CreateList<string>;
end;

destructor TJsonSchemaLoader.Destroy;
begin
  ResetState;
  FOwned := nil;
  FCache := nil;
  FResolving := nil;
  FExternalRoots := nil;
  FExternalJsonOwner := nil;
  FRefBaseStack := nil;
  inherited Destroy;
end;

procedure TJsonSchemaLoader.ResetState;
begin
  FRoot.Free;
  FRoot := nil;
  FBaseDir := '';
  FCache.Clear;
  FResolving.Clear;
  FExternalRoots.Clear;
  FExternalJsonOwner.Clear;
  FRefBaseStack.Clear;
end;

function TJsonSchemaLoader.CurrentRefBaseDir: string;
begin
  if FRefBaseStack.Count > 0 then
    Result := FRefBaseStack[FRefBaseStack.Count - 1]
  else
    Result := FBaseDir;
end;

procedure TJsonSchemaLoader.PushRefBaseDir(const Dir: string);
begin
  FRefBaseStack.Add(Dir);
end;

procedure TJsonSchemaLoader.PopRefBaseDir;
begin
  if FRefBaseStack.Count > 0 then
    FRefBaseStack.Delete(FRefBaseStack.Count - 1);
end;

function TJsonSchemaLoader.IsNullSchema(const Obj: TJSONObject): Boolean;
var
  TypeVal: TJSONValue;
begin
  Result := False;
  if not Assigned(Obj) then
    Exit;
  TypeVal := Obj.GetValue('type');
  if not Assigned(TypeVal) then
    Exit;
  if TypeVal is TJSONString then
    Result := SameText(TJSONString(TypeVal).Value, 'null')
  else if TypeVal is TJSONArray then
  begin
    for var I := 0 to TJSONArray(TypeVal).Count - 1 do
      if TJSONArray(TypeVal).Items[I] is TJSONString then
        if SameText(TJSONString(TJSONArray(TypeVal).Items[I]).Value, 'null') then
          Exit(True);
  end;
end;

function TJsonSchemaLoader.ParseType(const TypeVal: TJSONValue): TSchemaKind;
var
  S: string;
begin
  Result := skUnknown;
  if not Assigned(TypeVal) then
    Exit;
  if TypeVal is TJSONString then
  begin
    S := TJSONString(TypeVal).Value;
    if SameText(S, 'null') then Exit(skNull);
    if SameText(S, 'boolean') then Exit(skBoolean);
    if SameText(S, 'integer') then Exit(skInteger);
    if SameText(S, 'number') then Exit(skNumber);
    if SameText(S, 'string') then Exit(skString);
    if SameText(S, 'object') then Exit(skObject);
    if SameText(S, 'array') then Exit(skArray);
  end
  else if TypeVal is TJSONArray then
  begin
    for var I := 0 to TJSONArray(TypeVal).Count - 1 do
    begin
      if TJSONArray(TypeVal).Items[I] is TJSONString then
      begin
        S := TJSONString(TJSONArray(TypeVal).Items[I]).Value;
        if SameText(S, 'null') then
          Continue;
        Result := ParseType(TJSONArray(TypeVal).Items[I]);
        if Result <> skUnknown then
          Exit;
      end;
    end;
  end;
end;

function TJsonSchemaLoader.TryNormalizeNullableAnyOf(const Obj: TJSONObject;
  out Inner: TJSONObject): Boolean;
var
  AnyOf: TJSONArray;
  NonNull: TJSONObject;
  I: Integer;
  Branch: TJSONValue;
begin
  Result := False;
  Inner := nil;
  if not Assigned(Obj) then
    Exit;
  AnyOf := Obj.GetValue('anyOf') as TJSONArray;
  if not Assigned(AnyOf) then
    Exit;
  if AnyOf.Count <> 2 then
    Exit;
  NonNull := nil;
  for I := 0 to AnyOf.Count - 1 do
  begin
    Branch := AnyOf.Items[I];
    if not (Branch is TJSONObject) then
      Exit;
    if IsNullSchema(TJSONObject(Branch)) then
      Continue;
    if Assigned(NonNull) then
      Exit;
    NonNull := TJSONObject(Branch);
  end;
  if Assigned(NonNull) then
  begin
    Inner := NonNull;
    Result := True;
  end;
end;

function TJsonSchemaLoader.NewNode: TSchemaNode;
begin
  Result := TSchemaNode.Create;
  FOwned.Add(Result);
end;

procedure TJsonSchemaLoader.SplitRefParts(const Ref: string; out FilePart,
  FragmentPart: string);
var
  HashPos: Integer;
begin
  FilePart := '';
  FragmentPart := '';
  if Ref = '' then
    Exit;
  if Ref.StartsWith('#') then
  begin
    FragmentPart := Ref;
    Exit;
  end;
  HashPos := Ref.IndexOf('#');
  if HashPos >= 0 then
  begin
    FilePart := Copy(Ref, 1, HashPos);
    FragmentPart := Copy(Ref, HashPos + 1, MaxInt);
  end
  else
    FilePart := Ref;
end;

function TJsonSchemaLoader.ResolveSchemaFilePath(const FilePart: string): string;
var
  Candidate: string;
  BaseDir: string;
begin
  BaseDir := CurrentRefBaseDir;
  if BaseDir = '' then
    raise Exception.CreateFmt('Cannot resolve external $ref without a schema file path: %s',
      [FilePart]);
  if TPath.IsPathRooted(FilePart) then
    Candidate := TPath.GetFullPath(FilePart)
  else
    Candidate := TPath.GetFullPath(TPath.Combine(BaseDir, FilePart));
  if not TFile.Exists(Candidate) then
    raise Exception.CreateFmt('Cannot resolve $ref, schema file not found: %s', [Candidate]);
  Result := Candidate;
end;

function TJsonSchemaLoader.LoadExternalRoot(const AbsolutePath: string): TJSONObject;
var
  JsonText: string;
  Parsed: TJSONValue;
begin
  if FExternalRoots.TryGetValue(AbsolutePath, Result) then
    Exit;
  JsonText := TFile.ReadAllText(AbsolutePath, TEncoding.UTF8);
  Parsed := TJSONObject.ParseJSONValue(JsonText, False, True);
  if not (Parsed is TJSONObject) then
  begin
    Parsed.Free;
    raise Exception.CreateFmt('$ref schema root must be a JSON object: %s', [AbsolutePath]);
  end;
  FExternalJsonOwner.Add(Parsed);
  Result := TJSONObject(Parsed);
  FExternalRoots.Add(AbsolutePath, Result);
end;

function TJsonSchemaLoader.NavigateFragment(Root: TJSONValue;
  const FragmentPart: string): TJSONValue;
var
  Parts: IList<string>;
  Current: TJSONValue;
  I: Integer;
  Key: string;
  Segment: string;
  Clean: string;
begin
  if not Assigned(Root) then
    raise Exception.Create('Cannot navigate $ref fragment on nil root');
  if (FragmentPart = '') or (FragmentPart = '#') then
    Exit(Root);
  Clean := FragmentPart;
  if Clean.StartsWith('#/') then
    Clean := Copy(Clean, 3, MaxInt)
  else if Clean.StartsWith('#') then
    Clean := Copy(Clean, 2, MaxInt);
  if Clean = '' then
    Exit(Root);
  Parts := TCollections.CreateList<string>;
  try
    for Segment in Clean.Split(['/']) do
      if Segment <> '' then
        Parts.Add(Segment);
    Current := Root;
    for I := 0 to Parts.Count - 1 do
    begin
      Key := Parts[I];
      if not (Current is TJSONObject) then
        raise Exception.CreateFmt('Invalid $ref fragment path: %s', [FragmentPart]);
      Current := TJSONObject(Current).GetValue(Key);
      if not Assigned(Current) then
        raise Exception.CreateFmt('Invalid $ref fragment path: %s', [FragmentPart]);
    end;
    Result := Current;
  finally
    Parts := nil;
  end;
end;

procedure TJsonSchemaLoader.ApplyMetadata(const Obj: TJSONObject; Node: TSchemaNode);
var
  V: TJSONValue;
  EnumArr: TJSONArray;
  I: Integer;
begin
  if not Assigned(Obj) then
    Exit;
  V := Obj.GetValue('title');
  if V is TJSONString then
    Node.Title := TJSONString(V).Value;
  V := Obj.GetValue('description');
  if V is TJSONString then
    Node.Description := TJSONString(V).Value;
  V := Obj.GetValue('readOnly');
  if V is TJSONTrue then
    Node.ReadOnly := True
  else if V is TJSONFalse then
    Node.ReadOnly := False;
  V := Obj.GetValue('default');
  if Assigned(V) then
    Node.DefaultValue := V.Clone as TJSONValue;
  V := Obj.GetValue('enum');
  if V is TJSONArray then
  begin
    EnumArr := TJSONArray(V);
    Node.EnumValues.Clear;
    for I := 0 to EnumArr.Count - 1 do
      if EnumArr.Items[I] is TJSONString then
        Node.EnumValues.Add(TJSONString(EnumArr.Items[I]).Value)
      else
        Node.EnumValues.Add(EnumArr.Items[I].ToJSON);
  end;
  V := Obj.GetValue('minLength');
  if V is TJSONNumber then
    Node.MinLength := Trunc(TJSONNumber(V).AsDouble);
  V := Obj.GetValue('maxLength');
  if V is TJSONNumber then
    Node.MaxLength := Trunc(TJSONNumber(V).AsDouble);
  V := Obj.GetValue('minimum');
  if V is TJSONNumber then
  begin
    Node.Minimum := TJSONNumber(V).AsDouble;
    Node.HasMinimum := True;
  end;
  V := Obj.GetValue('maximum');
  if V is TJSONNumber then
  begin
    Node.Maximum := TJSONNumber(V).AsDouble;
    Node.HasMaximum := True;
  end;
end;

procedure TJsonSchemaLoader.ParseProperties(const Obj: TJSONObject; Node: TSchemaNode);
var
  Props: TJSONObject;
  RequiredArr: TJSONArray;
  RequiredSet: IDictionary<string, Boolean>;
  Pair: TJSONPair;
  PropNode: TSchemaNode;
  I: Integer;
  PropList: IList<TSchemaProperty>;
begin
  Props := Obj.GetValue('properties') as TJSONObject;
  if not Assigned(Props) then
    Exit;
  RequiredSet := TCollections.CreateDictionary<string, Boolean>;
  PropList := TCollections.CreateObjectList<TSchemaProperty>(True);
  try
    RequiredArr := Obj.GetValue('required') as TJSONArray;
    if Assigned(RequiredArr) then
      for I := 0 to RequiredArr.Count - 1 do
        if RequiredArr.Items[I] is TJSONString then
          RequiredSet[TJSONString(RequiredArr.Items[I]).Value] := True;
    for Pair in Props do
    begin
      if Pair.JsonValue is TJSONObject then
      begin
        PropNode := ResolveNode(TJSONObject(Pair.JsonValue), Pair.JsonString.Value);
        PropNode.Required := RequiredSet.ContainsKey(Pair.JsonString.Value);
        PropList.Add(TSchemaProperty.Create(Pair.JsonString.Value, PropNode));
      end;
    end;
    PropList.Sort(
      function(const Left, Right: TSchemaProperty): Integer
      var
        LT, RT: string;
      begin
        LT := TSchemaNode(Left.Node).Title;
        if LT = '' then
          LT := Left.Name;
        RT := TSchemaNode(Right.Node).Title;
        if RT = '' then
          RT := Right.Name;
        Result := CompareText(LT, RT);
      end);
    for var Prop in PropList do
      Node.AddProperty(Prop.Name, TSchemaNode(Prop.Node));
  finally
    PropList := nil;
    RequiredSet := nil;
  end;
end;

procedure TJsonSchemaLoader.ParseItems(const Obj: TJSONObject; Node: TSchemaNode);
var
  ItemsVal: TJSONValue;
begin
  ItemsVal := Obj.GetValue('items');
  if not Assigned(ItemsVal) then
    Exit;
  if ItemsVal is TJSONObject then
    Node.ItemsSchema := ResolveNode(TJSONObject(ItemsVal), 'items')
  else if ItemsVal is TJSONTrue then
  begin
    Node.ItemsSchema := NewNode;
    Node.ItemsSchema.Kind := skUnknown;
  end;
end;

procedure TJsonSchemaLoader.ParseAdditionalProperties(const Obj: TJSONObject;
  Node: TSchemaNode);
var
  AP: TJSONValue;
begin
  AP := Obj.GetValue('additionalProperties');
  if not Assigned(AP) then
    Exit;
  if AP is TJSONFalse then
  begin
    Node.AdditionalPropertiesAllowed := False;
    Exit;
  end;
  if AP is TJSONTrue then
  begin
    Node.AdditionalPropertiesAllowed := True;
    Node.Kind := skDictionary;
    Node.AdditionalPropertiesSchema := NewNode;
    Node.AdditionalPropertiesSchema.Kind := skUnknown;
    Exit;
  end;
  if AP is TJSONObject then
  begin
    Node.AdditionalPropertiesAllowed := True;
    if Node.Kind = skObject then
      Node.Kind := skDictionary;
    Node.AdditionalPropertiesSchema := ResolveNode(TJSONObject(AP), 'additionalProperties');
  end;
end;

procedure TJsonSchemaLoader.ParseOneOfDiscriminator(const Obj: TJSONObject;
  Node: TSchemaNode);
var
  OneOfArr: TJSONArray;
  Disc: TJSONObject;
  Mapping: TJSONObject;
  Pair: TJSONPair;
  BranchObj: TJSONObject;
  BranchNode: TSchemaNode;
  I: Integer;
begin
  OneOfArr := Obj.GetValue('oneOf') as TJSONArray;
  if not Assigned(OneOfArr) then
    Exit;
  Disc := Obj.GetValue('discriminator') as TJSONObject;
  if Assigned(Disc) then
  begin
    if Disc.GetValue('propertyName') is TJSONString then
      Node.DiscriminatorProperty := TJSONString(Disc.GetValue('propertyName')).Value;
    Mapping := Disc.GetValue('mapping') as TJSONObject;
    if Assigned(Mapping) then
      for Pair in Mapping do
        Node.DiscriminatorMapping[Pair.JsonString.Value] := Pair.JsonValue.Value;
  end;
  for I := 0 to OneOfArr.Count - 1 do
  begin
    if OneOfArr.Items[I] is TJSONObject then
    begin
      BranchObj := TJSONObject(OneOfArr.Items[I]);
      if BranchObj.GetValue('$ref') is TJSONString then
        BranchNode := ResolveNode(BranchObj, Format('oneOf[%d]', [I]))
      else
        BranchNode := ParseSchemaObject(BranchObj, Format('oneOf[%d]', [I]));
      Node.AddOneOfBranch(BranchNode);
    end;
  end;
  if Node.OneOfBranches.Count > 0 then
    Node.Kind := skObject;
end;

function TJsonSchemaLoader.ResolveNode(const Obj: TJSONObject;
  const RefKey: string): TSchemaNode;
var
  RefVal: TJSONString;
  RefPath: string;
  FilePart, FragmentPart: string;
  Target: TJSONValue;
  AbsolutePath: string;
begin
  RefVal := Obj.GetValue('$ref') as TJSONString;
  if Assigned(RefVal) then
  begin
    RefPath := RefVal.Value;
    if FCache.TryGetValue(RefPath, Result) then
      Exit;
    if FResolving.ContainsKey(RefPath) and FResolving[RefPath] then
    begin
      Result := NewNode;
      Result.RefPath := RefPath;
      Result.Kind := skObject;
      Result.ResolvedFromRef := True;
      FCache.Add(RefPath, Result);
      Exit;
    end;
    FResolving[RefPath] := True;
    try
      SplitRefParts(RefPath, FilePart, FragmentPart);
      if FilePart <> '' then
      begin
        AbsolutePath := ResolveSchemaFilePath(FilePart);
        PushRefBaseDir(TPath.GetDirectoryName(AbsolutePath));
        try
          Target := NavigateFragment(LoadExternalRoot(AbsolutePath), FragmentPart);
          if Target is TJSONObject then
            Result := ParseSchemaObject(TJSONObject(Target), RefPath)
          else
            raise Exception.CreateFmt('$ref target is not an object: %s', [RefPath]);
        finally
          PopRefBaseDir;
        end;
      end
      else
      begin
        Target := NavigateFragment(FRoot, FragmentPart);
        if Target is TJSONObject then
          Result := ParseSchemaObject(TJSONObject(Target), RefPath)
        else
          raise Exception.CreateFmt('$ref target is not an object: %s', [RefPath]);
      end;
      FCache[RefPath] := Result;
    finally
      FResolving[RefPath] := False;
    end;
    Exit;
  end;
  Result := ParseSchemaObject(Obj, RefKey);
end;

function TJsonSchemaLoader.ParseSchemaObject(const Obj: TJSONObject;
  const RefKey: string): TSchemaNode;
var
  Inner: TJSONObject;
  TypeVal: TJSONValue;
  NullableInner: TJSONObject;
  RefVal: TJSONString;
  Target: TJSONValue;
  FilePart, FragmentPart: string;
  AbsolutePath: string;
  PushedRefBase: Boolean;
begin
  if FCache.TryGetValue(RefKey, Result) then
    Exit;

  PushedRefBase := False;
  try
    Result := NewNode;
    if RefKey.StartsWith('#') or (Pos('#', RefKey) > 0) or (Pos('.json', LowerCase(RefKey)) > 0) then
      Result.RefPath := RefKey;

    if TryNormalizeNullableAnyOf(Obj, NullableInner) then
    begin
      Result.Nullable := True;
      ApplyMetadata(Obj, Result);
      RefVal := NullableInner.GetValue('$ref') as TJSONString;
      if Assigned(RefVal) then
      begin
        Result.RefPath := RefVal.Value;
        SplitRefParts(RefVal.Value, FilePart, FragmentPart);
        if FilePart <> '' then
        begin
          AbsolutePath := ResolveSchemaFilePath(FilePart);
          PushRefBaseDir(TPath.GetDirectoryName(AbsolutePath));
          PushedRefBase := True;
          Target := NavigateFragment(LoadExternalRoot(AbsolutePath), FragmentPart);
        end
        else
          Target := NavigateFragment(FRoot, FragmentPart);
        if not (Target is TJSONObject) then
          raise Exception.CreateFmt('$ref target is not an object: %s', [RefVal.Value]);
        Inner := TJSONObject(Target);
      end
      else
        Inner := NullableInner;
    end
    else
      Inner := Obj;

    ApplyMetadata(Inner, Result);
    TypeVal := Inner.GetValue('type');
    Result.Kind := ParseType(TypeVal);
    if Result.Kind = skUnknown then
    begin
      if Assigned(Inner.GetValue('properties')) or Assigned(Inner.GetValue('$ref')) then
        Result.Kind := skObject
      else if Assigned(Inner.GetValue('items')) then
        Result.Kind := skArray;
    end;
    if Inner.GetValue('type') is TJSONString then
      Result.JsonType := TJSONString(Inner.GetValue('type')).Value;

    ParseOneOfDiscriminator(Inner, Result);
    if Result.OneOfBranches.Count > 0 then
    begin
      if RefKey.StartsWith('#') or (Pos('.json', LowerCase(RefKey)) > 0) then
        FCache[RefKey] := Result;
      Exit;
    end;

    case Result.Kind of
      skObject:
        begin
          ParseProperties(Inner, Result);
          ParseAdditionalProperties(Inner, Result);
        end;
      skArray:
        ParseItems(Inner, Result);
      skDictionary:
        ParseAdditionalProperties(Inner, Result);
    end;

    if RefKey.StartsWith('#') or (Pos('.json', LowerCase(RefKey)) > 0) then
      FCache[RefKey] := Result;
  finally
    if PushedRefBase then
      PopRefBaseDir;
  end;
end;

function TJsonSchemaLoader.LoadFromJson(const Root: TJSONObject): TSchemaNode;
var
  SavedBaseDir: string;
begin
  SavedBaseDir := FBaseDir;
  ResetState;
  FBaseDir := SavedBaseDir;
  FRoot := Root.Clone as TJSONObject;
  Result := ResolveNode(FRoot, '#');
end;

function TJsonSchemaLoader.LoadFromString(const JsonText: string): TSchemaNode;
var
  Root: TJSONValue;
begin
  Root := TJSONObject.ParseJSONValue(JsonText, False, True);
  if not (Root is TJSONObject) then
  begin
    Root.Free;
    raise Exception.Create('Schema root must be a JSON object');
  end;
  try
    Result := LoadFromJson(TJSONObject(Root));
  finally
    Root.Free;
  end;
end;

function TJsonSchemaLoader.LoadFromFile(const Path: string): TSchemaNode;
begin
  FBaseDir := TPath.GetDirectoryName(TPath.GetFullPath(Path));
  Result := LoadFromString(TFile.ReadAllText(Path, TEncoding.UTF8));
end;

function TJsonSchemaLoader.LoadDocumentFromString(const JsonText: string): TSchemaDocument;
begin
  Result := TSchemaDocument.Create;
  Result.Root := LoadFromString(JsonText);
  Result.AdoptOwnedNodes(FOwned);
end;

function TJsonSchemaLoader.LoadDocumentFromFile(const Path: string): TSchemaDocument;
begin
  FBaseDir := TPath.GetDirectoryName(TPath.GetFullPath(Path));
  Result := TSchemaDocument.Create;
  Result.Root := LoadFromString(TFile.ReadAllText(Path, TEncoding.UTF8));
  Result.AdoptOwnedNodes(FOwned);
end;

end.
