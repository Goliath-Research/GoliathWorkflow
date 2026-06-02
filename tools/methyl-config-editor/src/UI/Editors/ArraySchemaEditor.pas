unit ArraySchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TArraySchemaEditor = class(TAbstractSchemaEditor)
  public
    class function EditorKey: string; static;
    function CanEdit(ANode: TSchemaNode): Boolean; override;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue); override;
    function EditValue(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue): TJSONValue; override;
  end;

implementation

uses
  ArrayEditorForm,
  ComplexRowSupport,
  SchemaValueSummary;

class function TArraySchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.ArrayKey;
end;

function TArraySchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skArray);
end;

procedure TArraySchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue);
begin
  TComplexRowSupport.BuildSummaryRow(AContext, ARow, AValue,
    procedure(Sender: TObject)
    var
      NewVal: TJSONValue;
    begin
      NewVal := EditValue(AContext, ARow, AContext.GetPropertyValue(ARow.PropertyName));
      if Assigned(NewVal) then
      begin
        AContext.SetPropertyValue(ARow.PropertyName, NewVal);
        UpdateSummary(ARow, NewVal);
      end;
    end,
    procedure(Sender: TObject)
    begin
      AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create);
      UpdateSummary(ARow, nil);
    end);
end;

function TArraySchemaEditor.EditValue(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue): TJSONValue;
var
  Arr: TJSONArray;
  Working: TJSONArray;
  ChildTitle: string;
  I: Integer;
begin
  Result := nil;
  if AValue is TJSONArray then
    Arr := TJSONArray(AValue)
  else
    Arr := TJSONArray.Create;
  Working := Arr.Clone as TJSONArray;
  try
    ChildTitle := AContext.ChildBreadcrumb(ARow.lblName.Caption);
    if TArrayEditorForm.EditArray(AContext.GetOwner, ChildTitle, ARow.SchemaNode, Working) then
    begin
      Result := Working.Clone as TJSONArray;
    end;
  finally
    Working.Free;
  end;
end;

end.
