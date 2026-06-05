unit PropertyEditorContext;

interface

uses
  System.Classes,
  System.JSON,
  System.SysUtils,
  SchemaNode,
  EditorTypes;

type
  TGetPropertyValueProc = reference to function(const AName: string): TJSONValue;
  TSetPropertyValueProc = reference to procedure(const AName: string; AValue: TJSONValue);
  TClearPropertyValueProc = reference to procedure(const AName: string);
  TRebuildRowsProc = reference to procedure;

  TPropertyEditorContext = class(TInterfacedObject, IPropertyEditorContext)
  private
    FOwner: TComponent;
    FObjectSchema: TSchemaNode;
    FBreadcrumb: string;
    FGetValue: TGetPropertyValueProc;
    FSetValue: TSetPropertyValueProc;
    FClearValue: TClearPropertyValueProc;
    FRebuild: TRebuildRowsProc;
  public
    constructor Create(AOwner: TComponent; AObjectSchema: TSchemaNode;
      const ABreadcrumb: string; const AGetValue: TGetPropertyValueProc;
      const ASetValue: TSetPropertyValueProc;
      const AClearValue: TClearPropertyValueProc;
      const ARebuild: TRebuildRowsProc);
    function GetOwner: TComponent;
    function GetObjectSchema: TSchemaNode;
    function GetBreadcrumb: string;
    function GetPropertyValue(const AName: string): TJSONValue;
    procedure SetPropertyValue(const AName: string; AValue: TJSONValue);
    procedure ClearPropertyValue(const AName: string);
    procedure RebuildRows;
    function ChildBreadcrumb(const ASegment: string): string;
  end;

implementation

constructor TPropertyEditorContext.Create(AOwner: TComponent;
  AObjectSchema: TSchemaNode; const ABreadcrumb: string;
  const AGetValue: TGetPropertyValueProc;
  const ASetValue: TSetPropertyValueProc;
  const AClearValue: TClearPropertyValueProc;
  const ARebuild: TRebuildRowsProc);
begin
  inherited Create;
  FOwner := AOwner;
  FObjectSchema := AObjectSchema;
  FBreadcrumb := ABreadcrumb;
  FGetValue := AGetValue;
  FSetValue := ASetValue;
  FClearValue := AClearValue;
  FRebuild := ARebuild;
end;

function TPropertyEditorContext.GetOwner: TComponent;
begin
  Result := FOwner;
end;

function TPropertyEditorContext.GetObjectSchema: TSchemaNode;
begin
  Result := FObjectSchema;
end;

function TPropertyEditorContext.GetBreadcrumb: string;
begin
  Result := FBreadcrumb;
end;

function TPropertyEditorContext.GetPropertyValue(const AName: string): TJSONValue;
begin
  Result := FGetValue(AName);
end;

procedure TPropertyEditorContext.SetPropertyValue(const AName: string;
  AValue: TJSONValue);
begin
  FSetValue(AName, AValue);
end;

procedure TPropertyEditorContext.ClearPropertyValue(const AName: string);
begin
  if Assigned(FClearValue) then
    FClearValue(AName);
end;

procedure TPropertyEditorContext.RebuildRows;
begin
  if Assigned(FRebuild) then
    FRebuild;
end;

function TPropertyEditorContext.ChildBreadcrumb(const ASegment: string): string;
begin
  if FBreadcrumb = '' then
    Result := ASegment
  else
    Result := FBreadcrumb + ' / ' + ASegment;
end;

end.
