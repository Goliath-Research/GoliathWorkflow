unit AbstractSchemaEditor;

interface

uses
  System.JSON,
  SchemaNode,
  EditorTypes,
  PropertyEditorContext;

type
  TAbstractSchemaEditor = class(TInterfacedObject, ISchemaPropertyEditor)
  public
    function CanEdit(ANode: TSchemaNode): Boolean; virtual;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue); virtual; abstract;
    procedure ReadRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow); virtual;
    procedure UpdateSummary(ARow: TPropertyRow; AValue: TJSONValue); virtual;
    function EditValue(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue): TJSONValue; virtual;
  end;

implementation

uses
  SchemaValueSummary,
  Vcl.StdCtrls;

function TAbstractSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := Assigned(ANode);
end;

procedure TAbstractSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
begin
  // default: inline editors write on change
end;

procedure TAbstractSchemaEditor.UpdateSummary(ARow: TPropertyRow;
  AValue: TJSONValue);
begin
  if ARow.ValueControl is TEdit then
    TEdit(ARow.ValueControl).Text := TSchemaValueSummary.Describe(ARow.SchemaNode, AValue);
end;

function TAbstractSchemaEditor.EditValue(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue): TJSONValue;
begin
  Result := nil;
end;

end.
