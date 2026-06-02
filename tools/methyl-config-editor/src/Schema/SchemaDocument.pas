unit SchemaDocument;

interface

uses
  System.Generics.Collections,
  System.SysUtils,
  SchemaNode;

type
  TSchemaDocument = class
  private
    FRoot: TSchemaNode;
    FOwnedNodes: TObjectList<TSchemaNode>;
  public
    constructor Create;
    destructor Destroy; override;
    procedure TakeOwnership(ANode: TSchemaNode);
    property Root: TSchemaNode read FRoot write FRoot;
  end;

implementation

constructor TSchemaDocument.Create;
begin
  inherited Create;
  FOwnedNodes := TObjectList<TSchemaNode>.Create(True);
end;

destructor TSchemaDocument.Destroy;
begin
  FRoot := nil;
  FOwnedNodes.Free;
  inherited Destroy;
end;

procedure TSchemaDocument.TakeOwnership(ANode: TSchemaNode);
begin
  if Assigned(ANode) and (FOwnedNodes.IndexOf(ANode) < 0) then
    FOwnedNodes.Add(ANode);
end;

end.
