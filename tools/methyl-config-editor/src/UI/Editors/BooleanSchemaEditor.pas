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
  Check.AllowGrayed := ARow.SchemaNode.Nullable or not ARow.SchemaNode.Required;
  if TSchemaValueSummary.IsNullValue(AValue) and Check.AllowGrayed then
    Check.State := cbGrayed
  else if AValue is TJSONTrue then
    Check.State := cbChecked
  else
    Check.State := cbUnchecked;
  Check.Tag := NativeInt(ARow);
  Check.OnClick := ARow.BindNotify(procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
    end);
  ARow.ValueControl := Check;
end;

procedure TBooleanSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
begin
  if not (ARow.ValueControl is TCheckBox) then
    Exit;
  case TCheckBox(ARow.ValueControl).State of
    cbGrayed:
      begin
        if ARow.SchemaNode.Nullable then
          AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create)
        else
          AContext.ClearPropertyValue(ARow.PropertyName);
      end;
    cbChecked:
      AContext.SetPropertyValue(ARow.PropertyName, TJSONTrue.Create);
  else
    AContext.SetPropertyValue(ARow.PropertyName, TJSONFalse.Create);
  end;
end;

end.
