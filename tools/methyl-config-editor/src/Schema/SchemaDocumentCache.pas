unit SchemaDocumentCache;

interface

uses
  Spring.Collections,
  System.SysUtils,
  SchemaDocument;

type
  TSchemaDocumentCache = class
  private
    FDocuments: IDictionary<string, TSchemaDocument>;
  public
    constructor Create;
    destructor Destroy; override;
    function TryGet(const APath: string; out ADocument: TSchemaDocument): Boolean;
    procedure Add(const APath: string; ADocument: TSchemaDocument);
    procedure Clear;
    function Count: Integer;
  end;

implementation

constructor TSchemaDocumentCache.Create;
begin
  inherited Create;
  FDocuments := TCollections.CreateDictionary<string, TSchemaDocument>;
end;

destructor TSchemaDocumentCache.Destroy;
begin
  Clear;
  FDocuments := nil;
  inherited Destroy;
end;

procedure TSchemaDocumentCache.Clear;
var
  Document: TSchemaDocument;
begin
  for Document in FDocuments.Values do
    Document.Free;
  FDocuments.Clear;
end;

function TSchemaDocumentCache.Count: Integer;
begin
  Result := FDocuments.Count;
end;

procedure TSchemaDocumentCache.Add(const APath: string; ADocument: TSchemaDocument);
begin
  FDocuments.Add(APath, ADocument);
end;

function TSchemaDocumentCache.TryGet(const APath: string;
  out ADocument: TSchemaDocument): Boolean;
begin
  Result := FDocuments.TryGetValue(APath, ADocument) and Assigned(ADocument);
end;

end.
