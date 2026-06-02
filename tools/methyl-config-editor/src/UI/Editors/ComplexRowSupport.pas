unit ComplexRowSupport;

interface

uses
  System.Classes,
  Vcl.Controls,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  System.JSON,
  EditorTypes,
  PropertyEditorContext,
  SchemaValueSummary;

type
  TComplexRowSupport = class
  public
    class procedure BuildSummaryRow(const AContext: IPropertyEditorContext;
      ARow: TPropertyRow; AValue: TJSONValue; AOnEdit: TNotifyEventProc;
      AOnClear: TNotifyEventProc);
  end;

implementation

class procedure TComplexRowSupport.BuildSummaryRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue; AOnEdit, AOnClear: TNotifyEventProc);
var
  Summary: TEdit;
begin
  Summary := TEdit.Create(ARow.ValuePanel);
  Summary.Parent := ARow.ValuePanel;
  Summary.Align := alClient;
  Summary.ReadOnly := True;
  Summary.Text := TSchemaValueSummary.Describe(ARow.SchemaNode, AValue);
  ARow.ValueControl := Summary;

  ARow.btnEdit := TButton.Create(ARow.ValuePanel);
  ARow.btnEdit.Parent := ARow.ValuePanel;
  ARow.btnEdit.Align := alRight;
  ARow.btnEdit.Width := 75;
  ARow.btnEdit.Caption := 'Edit...';
  ARow.btnEdit.Tag := NativeInt(ARow);
  ARow.btnEdit.OnClick := ARow.BindNotify(AOnEdit);

  if ARow.SchemaNode.Nullable then
  begin
    ARow.btnClear := TButton.Create(ARow.ValuePanel);
    ARow.btnClear.Parent := ARow.ValuePanel;
    ARow.btnClear.Align := alRight;
    ARow.btnClear.Width := 60;
    ARow.btnClear.Caption := 'Null';
    ARow.btnClear.Tag := NativeInt(ARow);
    ARow.btnClear.OnClick := ARow.BindNotify(AOnClear);
  end;
end;

end.
