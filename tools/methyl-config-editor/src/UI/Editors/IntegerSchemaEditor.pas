unit IntegerSchemaEditor;

interface

uses
  NumberSchemaEditor,
  SchemaEditorKeys;

type
  TIntegerSchemaEditor = class(TNumberSchemaEditor)
  public
    constructor Create;
    class function EditorKey: string; static;
  end;

implementation

constructor TIntegerSchemaEditor.Create;
begin
  inherited Create(True);
end;

class function TIntegerSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.IntegerKey;
end;

end.
