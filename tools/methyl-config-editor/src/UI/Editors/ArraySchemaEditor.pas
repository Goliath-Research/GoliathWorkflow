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
  Working: TJSONArray;
  ChildTitle: string;
begin
  Result := nil;
  if AValue is TJSONArray then
    Working := TJSONArray(AValue).Clone as TJSONArray
  else
    Working := TJSONArray.Create;
  try
    ChildTitle := AContext.ChildBreadcrumb(ARow.lblName.Caption);
    if TArrayEditorForm.EditArray(AContext.GetOwner, ChildTitle, ARow.SchemaNode, Working) then
      Result := Working.Clone as TJSONArray;
  finally
    Working.Free;
  end;
end;

end.
