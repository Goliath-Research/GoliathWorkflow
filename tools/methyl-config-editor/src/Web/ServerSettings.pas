unit ServerSettings;

interface

uses
  System.SysUtils,
  System.IniFiles,
  System.IOUtils;

type
  TServerSettings = class
  private
    FIniPath: string;
  public
    constructor Create(const AIniPath: string);
    function GetSchemasRoot: string;
    procedure SetSchemasRoot(const Value: string);
    function DefaultSchemasRoot: string;
    function GetPort: Integer;
    procedure SetPort(const Value: Integer);
  end;

implementation

constructor TServerSettings.Create(const AIniPath: string);
begin
  inherited Create;
  FIniPath := AIniPath;
end;

function TServerSettings.DefaultSchemasRoot: string;
var
  ExeDir: string;
begin
  ExeDir := ExtractFilePath(ParamStr(0));
  Result := TPath.GetFullPath(TPath.Combine(ExeDir, '..\..\schemas\config'));
  if not TDirectory.Exists(Result) then
    Result := TPath.GetFullPath(TPath.Combine(ExeDir, 'schemas\config'));
end;

function TServerSettings.GetPort: Integer;
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Result := Ini.ReadInteger('Server', 'Port', 8077);
  finally
    Ini.Free;
  end;
end;

procedure TServerSettings.SetPort(const Value: Integer);
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Ini.WriteInteger('Server', 'Port', Value);
  finally
    Ini.Free;
  end;
end;

function TServerSettings.GetSchemasRoot: string;
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Result := Ini.ReadString('Paths', 'SchemasRoot', DefaultSchemasRoot);
  finally
    Ini.Free;
  end;
end;

procedure TServerSettings.SetSchemasRoot(const Value: string);
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Ini.WriteString('Paths', 'SchemasRoot', Value);
  finally
    Ini.Free;
  end;
end;

end.
