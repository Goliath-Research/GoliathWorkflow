unit SchemaEditorRegistration;

interface

type
  TSchemaEditorRegistration = class
  private
    class var FRegistered: Boolean;
  public
    class procedure EnsureRegistered;
  end;

implementation

class procedure TSchemaEditorRegistration.EnsureRegistered;
begin
  if FRegistered then
    Exit;
  FRegistered := True;
end;

end.
