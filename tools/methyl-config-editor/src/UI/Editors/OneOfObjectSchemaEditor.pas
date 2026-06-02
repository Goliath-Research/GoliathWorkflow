unit OneOfObjectSchemaEditor;

interface

uses
  ObjectSchemaEditor,
  SchemaEditorKeys,
  SchemaNode;

type
  TOneOfObjectSchemaEditor = class(TObjectSchemaEditor)
  public
    class function EditorKey: string; static;
    function CanEdit(ANode: TSchemaNode): Boolean; override;
  end;

implementation

class function TOneOfObjectSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.OneOfObjectKey;
end;

function TOneOfObjectSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := Assigned(ANode) and (ANode.OneOfBranches.Count > 0);
end;

end.
