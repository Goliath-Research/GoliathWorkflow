unit DetectionStepEditor;

interface

uses
  ObjectSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TDetectionStepEditor = class(TObjectSchemaEditor)
  public
    class function EditorKey: string; static;
    class function SchemaTitle: string; static;
    class function StepId: string; static;
    function CanEdit(ANode: TSchemaNode): Boolean; override;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue); override;
    function EditValue(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue): TJSONValue; override;
  private
    class function DetectionSummary(AValue: TJSONValue): string;
    class function EffectiveSchema: TSchemaNode;
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

class function TDetectionStepEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.DetectionConfigKey;
end;

class function TDetectionStepEditor.SchemaTitle: string;
begin
  Result := 'MethylDetectorConfig';
end;

class function TDetectionStepEditor.StepId: string;
begin
  Result := 'detection';
end;

class function TDetectionStepEditor.EffectiveSchema: TSchemaNode;
begin
  if not TTypedStepSchemas.TryLoadStepRoot(StepId, Result) then
    raise Exception.Create('Detection schema is not available; set schemas root in the host app.');
end;

function TDetectionStepEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := Assigned(ANode) and (ANode.Kind = skObject) and
    (SameText(ANode.Title, SchemaTitle) or SameText(ANode.Title, 'MethylDetectorConfig'));
end;

class function TDetectionStepEditor.DetectionSummary(AValue: TJSONValue): string;
var
  Obj: TJSONObject;
  Chromosome, C1, C2: string;
begin
  if TSchemaValueSummary.IsNullValue(AValue) then
    Exit('(null)');
  if not (AValue is TJSONObject) then
    Exit(AValue.Value);
  Obj := TJSONObject(AValue);
  if Obj.GetValue('chromosome') is TJSONString then
    Chromosome := TJSONString(Obj.GetValue('chromosome')).Value
  else
    Chromosome := '?';
  if Obj.GetValue('centroid1_dir') is TJSONString then
    C1 := TJSONString(Obj.GetValue('centroid1_dir')).Value
  else
    C1 := '';
  if Obj.GetValue('centroid2_dir') is TJSONString then
    C2 := TJSONString(Obj.GetValue('centroid2_dir')).Value
  else
    C2 := '';
  if (C1 <> '') and (C2 <> '') then
    Result := Format('chromosome=%s; centroids set (%d fields)', [Chromosome, Obj.Count])
  else
    Result := Format('chromosome=%s (%d fields)', [Chromosome, Obj.Count]);
end;

procedure TDetectionStepEditor.CreateRow(const AContext: IPropertyEditorContext;
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
        if ARow.ValueControl is TEdit then
          TEdit(ARow.ValueControl).Text := DetectionSummary(NewVal);
      end;
    end,
    procedure(Sender: TObject)
    begin
      AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create);
      if ARow.ValueControl is TEdit then
        TEdit(ARow.ValueControl).Text := DetectionSummary(nil);
    end);
  if ARow.ValueControl is TEdit then
    TEdit(ARow.ValueControl).Text := DetectionSummary(AValue);
  ARow.lblName.Hint := 'MethylDetector step configuration (typed editor)';
end;

function TDetectionStepEditor.EditValue(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue): TJSONValue;
var
  CloneObj: TJSONObject;
  Schema: TSchemaNode;
  Title: string;
begin
  Result := nil;
  Schema := EffectiveSchema;
  if AValue is TJSONObject then
    CloneObj := TJSONObject(AValue).Clone as TJSONObject
  else
    CloneObj := TSchemaDefaults.CreateDefaultObject(Schema);
  try
    Title := AContext.ChildBreadcrumb('MethylDetector');
    if TPropertyEditorForm.EditObject(AContext.GetOwner, Title, Schema, CloneObj) then
      Result := CloneObj.Clone as TJSONObject;
  finally
    CloneObj.Free;
  end;
end;

end.
