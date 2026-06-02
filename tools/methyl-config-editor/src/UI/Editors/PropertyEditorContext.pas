unit PropertyEditorContext;

interface

uses
  System.Classes,
  System.JSON,
  System.SysUtils,
  SchemaNode,
  EditorTypes;

type
  TPropertyEditorContext = class(TInterfacedObject, IPropertyEditorContext)
  private
    FOwner: TComponent;
    FObjectSchema: TSchemaNode;
    FBreadcrumb: string;
    FGetValue: TFunc<string, TJSONValue>;
    FSetValue: TProc<string, TJSONValue>;
    FRebuild: TProc;
  public
    constructor Create(AOwner: TComponent; AObjectSchema: TSchemaNode;
      const ABreadcrumb: string; const AGetValue: TFunc<string, TJSONValue>;
      const ASetValue: TProc<string, TJSONValue>; const ARebuild: TProc);
    function GetOwner: TComponent;
    function GetObjectSchema: TSchemaNode;
    function GetBreadcrumb: string;
    function GetPropertyValue(const AName: string): TJSONValue;
    procedure SetPropertyValue(const AName: string; AValue: TJSONValue);
    procedure RebuildRows;
    function ChildBreadcrumb(const ASegment: string): string;
  end;

implementation

constructor TPropertyEditorContext.Create(AOwner: TComponent;
  AObjectSchema: TSchemaNode; const ABreadcrumb: string;
  const AGetValue: TFunc<string, TJSONValue>;
  const ASetValue: TProc<string, TJSONValue>; const ARebuild: TProc);
begin
  inherited Create;
  FOwner := AOwner;
  FObjectSchema := AObjectSchema;
  FBreadcrumb := ABreadcrumb;
  FGetValue := AGetValue;
  FSetValue := ASetValue;
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
    Result := FBreadcrumb + ' › ' + ASegment;
end;

end.
