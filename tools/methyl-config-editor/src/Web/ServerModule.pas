unit ServerModule;

interface

uses
  Classes,
  SysUtils,
  uniGUIMainModule,
  uniGUIApplication,
  uniGUICustomServer;

type
  TUniServerModule = class(TUniGUIServerModule)
  private
    { Private declarations }
  protected
    procedure FirstInit; override;
  end;

function UniServerModule: TUniServerModule;

implementation

{$R *.dfm}

uses
  UniGUIVars,
  ServerSettings,
  System.IOUtils;

function UniServerModule: TUniServerModule;
begin
  Result := TUniServerModule(UniGUIServerInstance);
end;

procedure TUniServerModule.FirstInit;
var
  Settings: TServerSettings;
  IniPath: string;
begin
  InitServerModule(Self);
  IniPath := TPath.Combine(ExtractFilePath(ParamStr(0)),
    'methyl-config-editor-web.ini');
  Settings := TServerSettings.Create(IniPath);
  try
    Port := Settings.GetPort;
  finally
    Settings.Free;
  end;
end;

initialization
  RegisterServerModuleClass(TUniServerModule);

end.
