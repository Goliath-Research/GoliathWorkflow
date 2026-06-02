unit DictionarySchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TDictionarySchemaEditor = class(TAbstractSchemaEditor)
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
  DictEditorForm;

class function TDictionarySchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.DictionaryKey;
end;

function TDictionarySchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skDictionary);
end;

procedure TDictionarySchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
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

function TDictionarySchemaEditor.EditValue(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue): TJSONValue;
var
  Working: TJSONObject;
  ChildTitle: string;
begin
  Result := nil;
  if AValue is TJSONObject then
    Working := TJSONObject(AValue).Clone as TJSONObject
  else
    Working := TJSONObject.Create;
  try
    ChildTitle := AContext.ChildBreadcrumb(ARow.lblName.Caption);
    if TDictEditorForm.EditDictionary(AContext.GetOwner, ChildTitle, ARow.SchemaNode,
      Working) then
      Result := Working.Clone as TJSONObject;
  finally
    Working.Free;
  end;
end;

end.
