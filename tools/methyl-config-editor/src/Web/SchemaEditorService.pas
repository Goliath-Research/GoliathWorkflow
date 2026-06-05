unit SchemaEditorService;

interface

uses
  System.JSON,
  SchemaNode,
  SchemaDefaults,
  SchemaValueSummary;

type
  TSchemaEditorService = class
  private
    class function EditWrappedRootValue(const ATitle: string; ASchema: TSchemaNode;
      ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
  public
    class function CanUseRootValue(AValue: TJSONValue; ASchema: TSchemaNode): Boolean;
    class function EditValue(const ATitle: string; ASchema: TSchemaNode;
      ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
    class function EditRootValue(const ATitle: string; ASchema: TSchemaNode;
      ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
  end;

implementation

uses
  NestedEditorForm,
  WebArrayEditorForm;

class function TSchemaEditorService.CanUseRootValue(AValue: TJSONValue;
  ASchema: TSchemaNode): Boolean;
begin
  Result := False;
  if not Assigned(AValue) or not Assigned(ASchema) then
    Exit;
  if TSchemaValueSummary.IsNullValue(AValue) then
    Exit(ASchema.Nullable or (ASchema.Kind = skNull));
  case ASchema.Kind of
    skNull:
      Result := AValue is TJSONNull;
    skBoolean:
      Result := (AValue is TJSONTrue) or (AValue is TJSONFalse);
    skInteger, skNumber:
      Result := AValue is TJSONNumber;
    skString:
      Result := AValue is TJSONString;
    skObject, skDictionary:
      Result := AValue is TJSONObject;
    skArray:
      Result := AValue is TJSONArray;
  else
    Result := True;
  end;
end;

class function TSchemaEditorService.EditWrappedRootValue(const ATitle: string;
  ASchema: TSchemaNode; ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
var
  WrapperSchema: TSchemaNode;
  WrapperObject: TJSONObject;
  Edited: TJSONObject;
begin
  Result := False;
  AEditedValue := nil;
  WrapperSchema := TSchemaNode.Create;
  WrapperObject := TJSONObject.Create;
  try
    WrapperSchema.Kind := skObject;
    WrapperSchema.Title := ATitle;
    WrapperSchema.AddProperty('value', ASchema);
    WrapperObject.AddPair('value', ASourceValue.Clone as TJSONValue);
    if TUniNestedEditorForm.EditObject(ATitle, WrapperSchema, WrapperObject, Edited) then
    begin
      try
        AEditedValue := Edited.GetValue('value').Clone as TJSONValue;
        Result := True;
      finally
        Edited.Free;
      end;
    end;
  finally
    WrapperObject.Free;
    WrapperSchema.Free;
  end;
end;

class function TSchemaEditorService.EditValue(const ATitle: string; ASchema: TSchemaNode;
  ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
var
  Working: TJSONValue;
  WorkingObj: TJSONObject;
  WorkingArr: TJSONArray;
  EditedObj: TJSONObject;
  EditedArr: TJSONArray;
begin
  Result := False;
  AEditedValue := nil;
  if CanUseRootValue(ASourceValue, ASchema) then
    Working := ASourceValue.Clone as TJSONValue
  else
    Working := TSchemaDefaults.CreateDefaultValue(ASchema);
  try
    if TSchemaValueSummary.IsNullValue(Working) then
      Exit(EditWrappedRootValue(ATitle, ASchema, Working, AEditedValue));
    case ASchema.Kind of
      skObject, skDictionary:
        begin
          if Working is TJSONObject then
            WorkingObj := TJSONObject(Working)
          else if ASchema.Kind = skObject then
            WorkingObj := TSchemaDefaults.CreateDefaultObject(ASchema)
          else
            WorkingObj := TJSONObject.Create;
          EditedObj := nil;
          try
            if TUniNestedEditorForm.EditObject(ATitle, ASchema, WorkingObj, EditedObj) then
            begin
              AEditedValue := EditedObj;
              EditedObj := nil;
              Result := True;
            end;
          finally
            EditedObj.Free;
            if WorkingObj <> Working then
              WorkingObj.Free;
          end;
        end;
      skArray:
        begin
          if Working is TJSONArray then
            WorkingArr := TJSONArray(Working)
          else
            WorkingArr := TJSONArray.Create;
          EditedArr := nil;
          try
            if TUniWebArrayEditorForm.EditArray(ATitle, ASchema, WorkingArr, EditedArr) then
            begin
              AEditedValue := EditedArr;
              EditedArr := nil;
              Result := True;
            end;
          finally
            EditedArr.Free;
            if WorkingArr <> Working then
              WorkingArr.Free;
          end;
        end;
    else
      Result := EditWrappedRootValue(ATitle, ASchema, Working, AEditedValue);
    end;
  finally
    Working.Free;
  end;
end;

class function TSchemaEditorService.EditRootValue(const ATitle: string;
  ASchema: TSchemaNode; ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
begin
  Result := EditValue(ATitle, ASchema, ASourceValue, AEditedValue);
end;

end.
