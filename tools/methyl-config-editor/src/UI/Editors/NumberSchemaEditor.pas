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
  System.SysUtils,
  Vcl.Controls,
  Vcl.StdCtrls,
  SchemaValueSummary;

function TryParseJsonFloat(const Text: string; out Value: Double): Boolean;
var
  FormatSettings: TFormatSettings;
begin
  Result := TryStrToFloat(Text, Value);
  if Result then
    Exit;
  FormatSettings := TFormatSettings.Create('en-US');
  Result := TryStrToFloat(Text, Value, FormatSettings);
end;

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
  Edit: TEdit;
begin
  Edit := TEdit.Create(ARow.ValuePanel);
  Edit.Parent := ARow.ValuePanel;
  Edit.Align := alClient;
  if AValue is TJSONNumber then
    Edit.Text := AValue.Value
  else if not TSchemaValueSummary.IsNullValue(AValue) then
    Edit.Text := AValue.Value;
  Edit.Tag := NativeInt(ARow);
  Edit.OnChange := ARow.BindNotify(procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
    end);
  ARow.ValueControl := Edit;
end;

procedure TNumberSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
var
  FloatValue: Double;
  IntValue: Int64;
  Text: string;
begin
  if not (ARow.ValueControl is TEdit) then
    Exit;

  Text := Trim(TEdit(ARow.ValueControl).Text);
  if Text = '' then
  begin
    if ARow.SchemaNode.Nullable then
      AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create)
    else
      AContext.ClearPropertyValue(ARow.PropertyName);
    Exit;
  end;

  if FIntegerMode then
  begin
    if TryStrToInt64(Text, IntValue) then
      AContext.SetPropertyValue(ARow.PropertyName, TJSONNumber.Create(IntValue))
    else if TryParseJsonFloat(Text, FloatValue) then
      AContext.SetPropertyValue(ARow.PropertyName, TJSONNumber.Create(FloatValue))
    else
      AContext.SetPropertyValue(ARow.PropertyName, TJSONString.Create(Text));
  end
  else if TryParseJsonFloat(Text, FloatValue) then
    AContext.SetPropertyValue(ARow.PropertyName,
      TJSONNumber.Create(FloatValue))
  else
    AContext.SetPropertyValue(ARow.PropertyName, TJSONString.Create(Text));
end;

end.
