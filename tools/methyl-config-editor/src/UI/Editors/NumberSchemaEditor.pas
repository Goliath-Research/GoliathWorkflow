unit NumberSchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TNumberSchemaEditor = class(TAbstractSchemaEditor)
  private
    FIntegerMode: Boolean;
  public
    constructor Create; overload;
    constructor Create(AIntegerMode: Boolean); overload;
    class function EditorKey: string; static;
    class function IntegerEditorKey: string; static;
    class function NumberEditorKey: string; static;
    function CanEdit(ANode: TSchemaNode): Boolean; override;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue); override;
    procedure ReadRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow); override;
  end;

implementation

uses
  Vcl.Controls,
  Vcl.Samples.Spin,
  Vcl.StdCtrls,
  NullableRowSupport,
  SchemaDefaults,
  SchemaValueSummary;

constructor TNumberSchemaEditor.Create;
begin
  inherited Create;
  FIntegerMode := False;
end;

constructor TNumberSchemaEditor.Create(AIntegerMode: Boolean);
begin
  inherited Create;
  FIntegerMode := AIntegerMode;
end;

class function TNumberSchemaEditor.EditorKey: string;
begin
  Result := NumberEditorKey;
end;

class function TNumberSchemaEditor.IntegerEditorKey: string;
begin
  Result := TSchemaEditorKeys.IntegerKey;
end;

class function TNumberSchemaEditor.NumberEditorKey: string;
begin
  Result := TSchemaEditorKeys.NumberKey;
end;

function TNumberSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  if not inherited CanEdit(ANode) then
    Exit(False);
  if FIntegerMode then
    Result := ANode.Kind = skInteger
  else
    Result := ANode.Kind = skNumber;
end;

procedure TNumberSchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue);
var
  Spin: TSpinEdit;
begin
  Spin := TSpinEdit.Create(ARow.ValuePanel);
  Spin.Parent := ARow.ValuePanel;
  Spin.Align := alClient;
  if AValue is TJSONNumber then
    Spin.Value := Trunc(TJSONNumber(AValue).AsDouble)
  else
    Spin.Value := 0;
  Spin.Tag := NativeInt(ARow);
  Spin.OnChange := ARow.BindNotify(procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
    end);
  ARow.ValueControl := Spin;
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

procedure TNumberSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
begin
  if TNullableRowSupport.IsNullChecked(ARow) then
  begin
    AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create);
    Exit;
  end;
  if ARow.ValueControl is TSpinEdit then
    AContext.SetPropertyValue(ARow.PropertyName,
      TJSONNumber.Create(TSpinEdit(ARow.ValueControl).Value));
end;

end.
