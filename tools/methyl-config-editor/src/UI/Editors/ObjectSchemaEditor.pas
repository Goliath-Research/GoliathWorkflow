unit ObjectSchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TObjectSchemaEditor = class(TAbstractSchemaEditor)
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
  ComplexRowSupport,
  PropertyEditorForm,
  SchemaDefaults,
  SchemaValueSummary;

class function TObjectSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.ObjectKey;
end;

function TObjectSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skObject) and
    (ANode.OneOfBranches.Count = 0);
end;

procedure TObjectSchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
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

function TObjectSchemaEditor.EditValue(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue): TJSONValue;
var
  CloneObj: TJSONObject;
  ChildTitle: string;
begin
  Result := nil;
  if AValue is TJSONObject then
    CloneObj := TJSONObject(AValue).Clone as TJSONObject
  else
    CloneObj := TSchemaDefaults.CreateDefaultObject(ARow.SchemaNode);
  try
    ChildTitle := AContext.ChildBreadcrumb(ARow.lblName.Caption);
    if TPropertyEditorForm.EditObject(AContext.GetOwner, ChildTitle, ARow.SchemaNode,
      CloneObj) then
      Result := CloneObj.Clone as TJSONObject;
  finally
    CloneObj.Free;
  end;
end;

end.
