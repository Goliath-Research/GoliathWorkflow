unit SchemaEditorKeys;

interface

uses
  SchemaNode;

type
  TSchemaEditorKeys = class
  public
    const
      BooleanKey = 'boolean';
      IntegerKey = 'integer';
      NumberKey = 'number';
      StringKey = 'string';
      EnumKey = 'enum';
      ObjectKey = 'object';
      OneOfObjectKey = 'oneOfObject';
      ArrayKey = 'array';
      DictionaryKey = 'dictionary';
      DiscriminatorKey = 'discriminator';
    class function ForNode(ANode: TSchemaNode): string;
  end;

implementation

class function TSchemaEditorKeys.ForNode(ANode: TSchemaNode): string;
begin
  if not Assigned(ANode) then
    Exit(StringKey);
  if (ANode.DiscriminatorProperty <> '') and (ANode.OneOfBranches.Count > 0) then
    Exit(OneOfObjectKey);
  case ANode.Kind of
    skBoolean:
      Exit(BooleanKey);
    skInteger:
      Exit(IntegerKey);
    skNumber:
      Exit(NumberKey);
    skString:
      if Length(ANode.EnumValues) > 0 then
        Exit(EnumKey)
      else
        Exit(StringKey);
    skObject:
      if ANode.OneOfBranches.Count > 0 then
        Exit(OneOfObjectKey)
      else
        Exit(ObjectKey);
    skArray:
      Exit(ArrayKey);
    skDictionary:
      Exit(DictionaryKey);
  else
    Exit(StringKey);
  end;
end;

end.
