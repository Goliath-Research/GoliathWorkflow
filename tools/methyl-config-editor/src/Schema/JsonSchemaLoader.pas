unit JsonSchemaLoader;

interface

uses
  System.Generics.Collections,
  System.JSON,
  System.SysUtils,
  SchemaNode;

type
  TJsonSchemaLoader = class
  private
    FRoot: TJSONObject;
    FCache: TDictionary<string, TSchemaNode>;
    FResolving: TDictionary<string, Boolean>;
    FOwned: TObjectList<TSchemaNode>;
    function NewNode: TSchemaNode;
    function ResolveRefPath(const Ref: string): TJSONValue;
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
  System.IOUtils,
  Generics.Defaults,
  SchemaDocument;

constructor TJsonSchemaLoader.Create;
begin
  inherited Create;
  FCache := TDictionary<string, TSchemaNode>.Create;
  FResolving := TDictionary<string, Boolean>.Create;
  FOwned := TObjectList<TSchemaNode>.Create(True);
end;

destructor TJsonSchemaLoader.Destroy;
begin
  FOwned.Free;
  FCache.Free;
  FResolving.Free;
  FRoot.Free;
  inherited Destroy;
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
      Exit; // more than one non-null branch
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

function TJsonSchemaLoader.ResolveRefPath(const Ref: string): TJSONValue;
var
  Parts: TArray<string>;
  Current: TJSONValue;
  I: Integer;
  Key: string;
begin
  Result := nil;
  if not Ref.StartsWith('#/') then
    raise Exception.CreateFmt('Unsupported $ref (external refs not supported): %s', [Ref]);
  Parts := Ref.Substring(2).Split(['/']);
  Current := FRoot;
  for I := 0 to High(Parts) do
  begin
    Key := Parts[I];
    if not (Current is TJSONObject) then
      raise Exception.CreateFmt('Invalid $ref path: %s', [Ref]);
    Current := TJSONObject(Current).GetValue(Key);
    if not Assigned(Current) then
      raise Exception.CreateFmt('Invalid $ref path: %s', [Ref]);
  end;
  Result := Current;
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
    SetLength(Node.EnumValues, EnumArr.Count);
    for I := 0 to EnumArr.Count - 1 do
      if EnumArr.Items[I] is TJSONString then
        Node.EnumValues[I] := TJSONString(EnumArr.Items[I]).Value
      else
        Node.EnumValues[I] := EnumArr.Items[I].ToJSON;
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
  RequiredSet: TDictionary<string, Boolean>;
  Pair: TJSONPair;
  PropNode: TSchemaNode;
  I: Integer;
  PropList: TObjectList<TSchemaProperty>;
  Compare: TComparison<TSchemaProperty>;
begin
  Props := Obj.GetValue('properties') as TJSONObject;
  if not Assigned(Props) then
    Exit;
  RequiredSet := TDictionary<string, Boolean>.Create;
  PropList := TObjectList<TSchemaProperty>.Create(True);
  try
    RequiredArr := Obj.GetValue('required') as TJSONArray;
    if Assigned(RequiredArr) then
      for I := 0 to RequiredArr.Count - 1 do
        if RequiredArr.Items[I] is TJSONString then
          RequiredSet.AddOrSetValue(TJSONString(RequiredArr.Items[I]).Value, True);
    for Pair in Props do
    begin
      if Pair.JsonValue is TJSONObject then
      begin
        PropNode := ResolveNode(TJSONObject(Pair.JsonValue), Pair.JsonString.Value);
        PropNode.Required := RequiredSet.ContainsKey(Pair.JsonString.Value);
        PropList.Add(TSchemaProperty.Create(Pair.JsonString.Value, PropNode));
      end;
    end;
    Compare := function(const Left, Right: TSchemaProperty): Integer
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
      end;
    PropList.Sort(TComparer<TSchemaProperty>.Construct(Compare));
    for var Prop in PropList do
      Node.AddProperty(Prop.Name, TSchemaNode(Prop.Node));
    PropList.OwnsObjects := False;
  finally
    PropList.Free;
    RequiredSet.Free;
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
    Node.ItemsSchema := TSchemaNode.Create;
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
    Node.AdditionalPropertiesSchema := TSchemaNode.Create;
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
        Node.DiscriminatorMapping.AddOrSetValue(Pair.JsonString.Value, Pair.JsonValue.Value);
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
  Target: TJSONValue;
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
    FResolving.AddOrSetValue(RefPath, True);
    try
      Target := ResolveRefPath(RefPath);
      if Target is TJSONObject then
        Result := ParseSchemaObject(TJSONObject(Target), RefPath)
      else
        raise Exception.CreateFmt('$ref target is not an object: %s', [RefPath]);
      FCache.AddOrSetValue(RefPath, Result);
    finally
      FResolving.AddOrSetValue(RefPath, False);
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
begin
  if FCache.TryGetValue(RefKey, Result) then
    Exit;

  Result := NewNode;
  if RefKey.StartsWith('#') then
    Result.RefPath := RefKey;

  if TryNormalizeNullableAnyOf(Obj, NullableInner) then
  begin
    Result.Nullable := True;
    Inner := NullableInner;
    ApplyMetadata(Obj, Result);
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
    if RefKey.StartsWith('#') then
      FCache.AddOrSetValue(RefKey, Result);
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

  if RefKey.StartsWith('#') then
    FCache.AddOrSetValue(RefKey, Result);
end;

function TJsonSchemaLoader.LoadFromJson(const Root: TJSONObject): TSchemaNode;
begin
  FRoot := Root.Clone as TJSONObject;
  FCache.Clear;
  FResolving.Clear;
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
  Result := LoadFromString(TFile.ReadAllText(Path, TEncoding.UTF8));
end;

function TJsonSchemaLoader.LoadDocumentFromString(const JsonText: string): TSchemaDocument;
var
  Node: TSchemaNode;
begin
  Node := LoadFromString(JsonText);
  Result := TSchemaDocument.Create;
  Result.Root := Node;
  while FOwned.Count > 0 do
  begin
    Result.TakeOwnership(FOwned[0]);
    FOwned.Extract(FOwned[0]);
  end;
end;

function TJsonSchemaLoader.LoadDocumentFromFile(const Path: string): TSchemaDocument;
begin
  Result := LoadDocumentFromString(TFile.ReadAllText(Path, TEncoding.UTF8));
end;

end.
