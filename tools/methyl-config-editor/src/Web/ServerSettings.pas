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
    function GetGatewayEnabled: Boolean;
    procedure SetGatewayEnabled(const Value: Boolean);
    function GetGatewayBaseUrl: string;
    procedure SetGatewayBaseUrl(const Value: string);
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

function TServerSettings.GetGatewayEnabled: Boolean;
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Result := Ini.ReadBool('Gateway', 'Enabled', False);
  finally
    Ini.Free;
  end;
end;

procedure TServerSettings.SetGatewayEnabled(const Value: Boolean);
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Ini.WriteBool('Gateway', 'Enabled', Value);
  finally
    Ini.Free;
  end;
end;

function TServerSettings.GetGatewayBaseUrl: string;
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Result := Ini.ReadString('Gateway', 'BaseUrl', 'http://localhost:8080/v1');
  finally
    Ini.Free;
  end;
end;

procedure TServerSettings.SetGatewayBaseUrl(const Value: string);
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Ini.WriteString('Gateway', 'BaseUrl', Value);
  finally
    Ini.Free;
  end;
end;

end.
