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

uses
  Winapi.Windows;

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
  Summary.OnKeyDown := ARow.BindKeyDown(procedure(Sender: TObject;
    var Key: Word; Shift: TShiftState)
    begin
      if Key in [VK_BACK, VK_DELETE] then
      begin
        AOnClear(Sender);
        Key := 0;
      end;
    end);
  ARow.ValueControl := Summary;

  ARow.btnEdit := TButton.Create(ARow.ValuePanel);
  ARow.btnEdit.Parent := ARow.ValuePanel;
  ARow.btnEdit.Align := alRight;
  ARow.btnEdit.Width := 28;
  ARow.btnEdit.Caption := '...';
  ARow.btnEdit.Tag := NativeInt(ARow);
  ARow.btnEdit.OnClick := ARow.BindNotify(AOnEdit);
end;

end.
