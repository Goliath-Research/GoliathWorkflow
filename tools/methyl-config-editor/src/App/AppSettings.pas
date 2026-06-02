unit AppSettings;

interface

uses
  System.SysUtils,
  System.IniFiles,
  System.IOUtils;

type
  TAppSettings = class
  private
    FIniPath: string;
  public
    constructor Create(const AIniPath: string);
    function GetSchemasRoot: string;
    procedure SetSchemasRoot(const Value: string);
    function GetLastSchemaPath: string;
    procedure SetLastSchemaPath(const Value: string);
    function GetLastDocumentPath: string;
    procedure SetLastDocumentPath(const Value: string);
    function DefaultSchemasRoot: string;
  end;

implementation

function TAppSettings.DefaultSchemasRoot: string;
var
  ExeDir: string;
begin
  ExeDir := ExtractFilePath(ParamStr(0));
  Result := TPath.GetFullPath(TPath.Combine(ExeDir, '..\..\..\schemas\config'));
  if not TDirectory.Exists(Result) then
    Result := TPath.GetFullPath(TPath.Combine(ExeDir, 'schemas\config'));
end;

constructor TAppSettings.Create(const AIniPath: string);
begin
  inherited Create;
  FIniPath := AIniPath;
end;

function TAppSettings.GetSchemasRoot: string;
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

procedure TAppSettings.SetSchemasRoot(const Value: string);
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

function TAppSettings.GetLastSchemaPath: string;
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Result := Ini.ReadString('Recent', 'LastSchema', '');
  finally
    Ini.Free;
  end;
end;

procedure TAppSettings.SetLastSchemaPath(const Value: string);
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Ini.WriteString('Recent', 'LastSchema', Value);
  finally
    Ini.Free;
  end;
end;

function TAppSettings.GetLastDocumentPath: string;
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Result := Ini.ReadString('Recent', 'LastDocument', '');
  finally
    Ini.Free;
  end;
end;

procedure TAppSettings.SetLastDocumentPath(const Value: string);
var
  Ini: TIniFile;
begin
  Ini := TIniFile.Create(FIniPath);
  try
    Ini.WriteString('Recent', 'LastDocument', Value);
  finally
    Ini.Free;
  end;
end;

end.
