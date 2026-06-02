unit BooleanSchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TBooleanSchemaEditor = class(TAbstractSchemaEditor)
  public
    class function EditorKey: string; static;
    function CanEdit(ANode: TSchemaNode): Boolean; override;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue); override;
    procedure ReadRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow); override;
  end;

implementation

uses
  Vcl.Controls,
  Vcl.StdCtrls,
  NullableRowSupport,
  SchemaDefaults,
  SchemaValueSummary;

class function TBooleanSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.BooleanKey;
end;

function TBooleanSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skBoolean);
end;

procedure TBooleanSchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue);
var
  Check: TCheckBox;
begin
  Check := TCheckBox.Create(ARow.ValuePanel);
  Check.Parent := ARow.ValuePanel;
  Check.Align := alClient;
  Check.Caption := '';
  Check.Checked := AValue is TJSONTrue;
  Check.Tag := NativeInt(ARow);
  Check.OnClick := ARow.BindNotify(procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
    end);
  ARow.ValueControl := Check;
  TNullableRowSupport.AddNullCheckbox(AContext, ARow, AValue,
    procedure(Sender: TObject)
    begin
      if TNullableRowSupport.IsNullChecked(ARow) then
      begin
        AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create);
        TNullableRowSupport.SetControlEnabled(ARow, False);
      end
      else
      begin
        AContext.SetPropertyValue(ARow.PropertyName,
          TSchemaDefaults.CreateDefaultValue(ARow.SchemaNode));
        TNullableRowSupport.SetControlEnabled(ARow, True);
        CreateRow(AContext, ARow, AContext.GetPropertyValue(ARow.PropertyName));
      end;
    end);
  TNullableRowSupport.SetControlEnabled(ARow, not TNullableRowSupport.IsNullChecked(ARow));
end;

procedure TBooleanSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
begin
  if TNullableRowSupport.IsNullChecked(ARow) then
  begin
    AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create);
    Exit;
  end;
  if TCheckBox(ARow.ValueControl).Checked then
    AContext.SetPropertyValue(ARow.PropertyName, TJSONTrue.Create)
  else
    AContext.SetPropertyValue(ARow.PropertyName, TJSONFalse.Create);
end;

end.
