unit TypedStepSchemaEditor;

interface

uses
  ObjectSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaNode,
  System.JSON;

type
  TTypedStepSchemaEditor = class(TObjectSchemaEditor)
  private
    FStepId: string;
    class function EffectiveSchema(const AStepId: string): TSchemaNode;
  public
    constructor Create(const AStepId: string);
    class function StepIdFromNode(ANode: TSchemaNode): string;
    function CanEdit(ANode: TSchemaNode): Boolean; override;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue); override;
    function EditValue(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue): TJSONValue; override;
  end;

implementation

uses
  System.SysUtils,
  Vcl.StdCtrls,
  ComplexRowSupport,
  PropertyEditorForm,
  SchemaDefaults,
  SchemaValueSummary,
  TypedStepSchemas;

constructor TTypedStepSchemaEditor.Create(const AStepId: string);
begin
  inherited Create;
  FStepId := AStepId;
end;

class function TTypedStepSchemaEditor.StepIdFromNode(ANode: TSchemaNode): string;
begin
  Result := TTypedStepSchemas.TryGetStepIdForTitle(ANode.Title);
end;

class function TTypedStepSchemaEditor.EffectiveSchema(const AStepId: string): TSchemaNode;
begin
  if not TTypedStepSchemas.TryLoadStepRoot(AStepId, Result) then
    raise Exception.CreateFmt(
      'Step schema "%s" is not available; set schemas root in the host app.', [AStepId]);
end;

function TTypedStepSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
var
  StepId: string;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skObject);
  if not Result then
    Exit;
  StepId := StepIdFromNode(ANode);
  Result := (StepId <> '') and TTypedStepSchemas.HasStepSchema(StepId);
end;

procedure TTypedStepSchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
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
  if ARow.SchemaNode.Title <> '' then
    ARow.lblName.Hint := Format('Typed step editor (%s)', [FStepId]);
end;

function TTypedStepSchemaEditor.EditValue(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue): TJSONValue;
var
  CloneObj: TJSONObject;
  Schema: TSchemaNode;
  Title: string;
begin
  Result := nil;
  Schema := EffectiveSchema(FStepId);
  if AValue is TJSONObject then
    CloneObj := TJSONObject(AValue).Clone as TJSONObject
  else
    CloneObj := TSchemaDefaults.CreateDefaultObject(Schema);
  try
    if Schema.Title <> '' then
      Title := AContext.ChildBreadcrumb(Schema.Title)
    else
      Title := AContext.ChildBreadcrumb(FStepId);
    if TPropertyEditorForm.EditObject(AContext.GetOwner, Title, Schema, CloneObj) then
      Result := CloneObj.Clone as TJSONObject;
  finally
    CloneObj.Free;
  end;
end;

end.
