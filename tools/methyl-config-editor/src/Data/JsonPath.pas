unit JsonPath;

interface

uses
  Spring.Collections,
  System.JSON,
  System.SysUtils;

type
  TJsonPath = class
  public
    class function SplitPath(const Path: string): IList<string>;
    class function GetValue(Root: TJSONValue; const Path: string): TJSONValue;
    class function GetObject(Root: TJSONValue; const Path: string): TJSONObject;
    class function GetArray(Root: TJSONValue; const Path: string): TJSONArray;
    class function EnsureObject(Root: TJSONValue; const Path: string): TJSONObject;
    class function EnsureArray(Root: TJSONValue; const Path: string): TJSONArray;
    class procedure SetValue(Root: TJSONValue; const Path: string; Value: TJSONValue);
    class function CloneValue(Value: TJSONValue): TJSONValue;
    class function JoinPath(const Base, Segment: string): string;
  end;

implementation

procedure SetArrayElement(Arr: TJSONArray; Index: Integer; Value: TJSONValue);
var
  I: Integer;
  Tail: IList<TJSONValue>;
begin
  if Index < 0 then
    raise Exception.Create('Negative array index');
  while Arr.Count <= Index do
    Arr.AddElement(TJSONNull.Create);
  Tail := TCollections.CreateObjectList<TJSONValue>(False);
  try
    for I := Index + 1 to Arr.Count - 1 do
      Tail.Add(Arr.Items[I].Clone as TJSONValue);
    while Arr.Count > Index do
    begin
      Arr.Items[Arr.Count - 1].Free;
      Arr.Remove(Arr.Count - 1);
    end;
    Arr.AddElement(Value);
    for I := 0 to Tail.Count - 1 do
      Arr.AddElement(Tail[I]);
  finally
    Tail := nil;
  end;
end;

class function TJsonPath.SplitPath(const Path: string): IList<string>;
var
  Clean: string;
  Part: string;
begin
  Result := TCollections.CreateList<string>;
  Clean := Path;
  if Clean.StartsWith('/') then
    Clean := Copy(Clean, 2, MaxInt);
  if Clean = '' then
    Exit;
  for Part in Clean.Split(['/']) do
    if Part <> '' then
      Result.Add(Part);
end;

class function TJsonPath.JoinPath(const Base, Segment: string): string;
begin
  if Base = '' then
    Result := Segment
  else
    Result := Base + '/' + Segment;
end;

class function TJsonPath.GetValue(Root: TJSONValue; const Path: string): TJSONValue;
var
  Segments: IList<string>;
  Current: TJSONValue;
  I: Integer;
  Idx: Integer;
begin
  Result := nil;
  if not Assigned(Root) then
    Exit;
  Segments := SplitPath(Path);
  if Segments.Count = 0 then
    Exit(Root);
  Current := Root;
  for I := 0 to Segments.Count - 1 do
  begin
    if not Assigned(Current) then
      Exit(nil);
    if Current is TJSONObject then
      Current := TJSONObject(Current).GetValue(Segments[I])
    else if Current is TJSONArray then
    begin
      if not TryStrToInt(Segments[I], Idx) then
        Exit(nil);
      if (Idx < 0) or (Idx >= TJSONArray(Current).Count) then
        Exit(nil);
      Current := TJSONArray(Current).Items[Idx];
    end
    else
      Exit(nil);
  end;
  Result := Current;
end;

class function TJsonPath.GetObject(Root: TJSONValue; const Path: string): TJSONObject;
var
  V: TJSONValue;
begin
  V := GetValue(Root, Path);
  if V is TJSONObject then
    Result := TJSONObject(V)
  else
    Result := nil;
end;

class function TJsonPath.GetArray(Root: TJSONValue; const Path: string): TJSONArray;
var
  V: TJSONValue;
begin
  V := GetValue(Root, Path);
  if V is TJSONArray then
    Result := TJSONArray(V)
  else
    Result := nil;
end;

class function TJsonPath.EnsureObject(Root: TJSONValue; const Path: string): TJSONObject;
var
  Segments: IList<string>;
  Current: TJSONValue;
  NextObj: TJSONObject;
  I, Idx: Integer;
  Existing: TJSONValue;
begin
  if not Assigned(Root) then
    raise Exception.Create('Root JSON value is nil');
  Segments := SplitPath(Path);
  if Segments.Count = 0 then
  begin
    if Root is TJSONObject then
      Exit(TJSONObject(Root));
    raise Exception.Create('Root is not an object');
  end;
  Current := Root;
  for I := 0 to Segments.Count - 1 do
  begin
    if Current is TJSONObject then
    begin
      Existing := TJSONObject(Current).GetValue(Segments[I]);
      if not Assigned(Existing) then
      begin
        if I = Segments.Count - 1 then
        begin
          NextObj := TJSONObject.Create;
          TJSONObject(Current).AddPair(Segments[I], NextObj);
          Exit(NextObj);
        end;
        NextObj := TJSONObject.Create;
        TJSONObject(Current).AddPair(Segments[I], NextObj);
        Current := NextObj;
      end
      else
        Current := Existing;
    end
    else if Current is TJSONArray then
    begin
      if not TryStrToInt(Segments[I], Idx) then
        raise Exception.CreateFmt('Invalid array index in path: %s', [Path]);
      while TJSONArray(Current).Count <= Idx do
        TJSONArray(Current).AddElement(TJSONNull.Create);
      Current := TJSONArray(Current).Items[Idx];
    end
    else
      raise Exception.CreateFmt('Cannot traverse path through non-container: %s', [Path]);
  end;
  if Current is TJSONObject then
    Result := TJSONObject(Current)
  else
  begin
    NextObj := TJSONObject.Create;
    if Current is TJSONArray then
    begin
      Idx := StrToIntDef(Segments[Segments.Count - 1], -1);
      SetArrayElement(TJSONArray(Current), Idx, NextObj);
    end
    else
      raise Exception.CreateFmt('Path does not resolve to object: %s', [Path]);
    Result := NextObj;
  end;
end;

class function TJsonPath.EnsureArray(Root: TJSONValue; const Path: string): TJSONArray;
var
  Obj: TJSONObject;
  Segments: IList<string>;
  Last: string;
  ParentPath: string;
  I: Integer;
  Existing: TJSONValue;
begin
  Segments := SplitPath(Path);
  if Segments.Count = 0 then
    raise Exception.Create('Empty path for array');
  Last := Segments[Segments.Count - 1];
  ParentPath := '';
  for I := 0 to Segments.Count - 2 do
    ParentPath := JoinPath(ParentPath, Segments[I]);
  if ParentPath = '' then
  begin
    if not (Root is TJSONObject) then
      raise Exception.Create('Root is not an object');
    Obj := TJSONObject(Root);
  end
  else
  begin
    Obj := EnsureObject(Root, ParentPath);
  end;
  Existing := Obj.GetValue(Last);
  if Existing is TJSONArray then
    Exit(TJSONArray(Existing));
  if Assigned(Existing) then
    Obj.RemovePair(Last).Free;
  Result := TJSONArray.Create;
  Obj.AddPair(Last, Result);
end;

class procedure TJsonPath.SetValue(Root: TJSONValue; const Path: string;
  Value: TJSONValue);
var
  Segments: IList<string>;
  Current: TJSONValue;
  I, Idx: Integer;
  Key: string;
  Arr: TJSONArray;
begin
  if not Assigned(Root) then
    raise Exception.Create('Root JSON value is nil');
  Segments := SplitPath(Path);
  if Segments.Count = 0 then
    raise Exception.Create('Cannot set root via path');
  Current := Root;
  for I := 0 to Segments.Count - 1 do
  begin
    Key := Segments[I];
    if I = Segments.Count - 1 then
    begin
      if Current is TJSONObject then
      begin
        if TJSONObject(Current).GetValue(Key) <> nil then
          TJSONObject(Current).RemovePair(Key).Free;
        TJSONObject(Current).AddPair(Key, Value);
      end
      else if Current is TJSONArray then
      begin
        if not TryStrToInt(Key, Idx) then
          raise Exception.CreateFmt('Invalid array index: %s', [Key]);
        Arr := TJSONArray(Current);
        while Arr.Count <= Idx do
          Arr.AddElement(TJSONNull.Create);
        SetArrayElement(Arr, Idx, Value);
      end
      else
        raise Exception.Create('Cannot set value on non-container');
      Exit;
    end;
    if Current is TJSONObject then
    begin
      if not Assigned(TJSONObject(Current).GetValue(Key)) then
        TJSONObject(Current).AddPair(Key, TJSONObject.Create);
      Current := TJSONObject(Current).GetValue(Key);
    end
    else if Current is TJSONArray then
    begin
      if not TryStrToInt(Key, Idx) then
        raise Exception.CreateFmt('Invalid array index: %s', [Key]);
      Arr := TJSONArray(Current);
      while Arr.Count <= Idx do
        Arr.AddElement(TJSONObject.Create);
      if not (Arr.Items[Idx] is TJSONObject) then
        SetArrayElement(Arr, Idx, TJSONObject.Create);
      Current := Arr.Items[Idx];
    end
    else
      raise Exception.CreateFmt('Invalid path segment: %s', [Path]);
  end;
end;

class function TJsonPath.CloneValue(Value: TJSONValue): TJSONValue;
begin
  if not Assigned(Value) then
    Exit(nil);
  Result := Value.Clone as TJSONValue;
end;

end.
