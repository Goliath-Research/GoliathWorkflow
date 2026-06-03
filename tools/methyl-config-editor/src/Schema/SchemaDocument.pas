unit SchemaDocument;

interface

uses
  Spring.Collections,
  System.SysUtils,
  SchemaNode;

type
  TSchemaDocument = class
  private
    FRoot: TSchemaNode;
    FOwnedNodes: IList<TSchemaNode>;
  public
    constructor Create;
    destructor Destroy; override;
    procedure AdoptOwnedNodes(var AList: IList<TSchemaNode>);
    property Root: TSchemaNode read FRoot write FRoot;
  end;

implementation

constructor TSchemaDocument.Create;
begin
  inherited Create;
  FOwnedNodes := TCollections.CreateObjectList<TSchemaNode>(True);
end;

destructor TSchemaDocument.Destroy;
begin
  FRoot := nil;
  FOwnedNodes := nil;
  inherited Destroy;
end;

procedure TSchemaDocument.AdoptOwnedNodes(var AList: IList<TSchemaNode>);
begin
  FOwnedNodes := AList;
  AList := TCollections.CreateObjectList<TSchemaNode>(True);
end;

end.
