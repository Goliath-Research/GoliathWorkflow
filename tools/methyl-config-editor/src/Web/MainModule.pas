unit MainModule;

interface

uses
  uniGUIMainModule,
  SysUtils,
  Classes,
  SchemaCatalog,
  SchemaDocument,
  JsonDocumentModel,
  ServerSettings;

type
  TUniMainModule = class(TUniGUIMainModule)
  private
    FSettings: TServerSettings;
    FCatalog: TSchemaCatalog;
    FSchemaDoc: TSchemaDocument;
    FDocument: TJsonDocumentModel;
    FHasJsonValue: Boolean;
    FUploadedFileName: string;
  public
    constructor Create(AOwner: TComponent); override;
    destructor Destroy; override;
    procedure ReloadCatalog;
    procedure LoadSelectedSchema(const SchemaPath: string);
    function SchemaTitle: string;
    function CurrentSchemaPath(const SchemaIndex: Integer): string;
    property Settings: TServerSettings read FSettings;
    property Catalog: TSchemaCatalog read FCatalog;
    property SchemaDoc: TSchemaDocument read FSchemaDoc;
    property Document: TJsonDocumentModel read FDocument;
    property HasJsonValue: Boolean read FHasJsonValue write FHasJsonValue;
    property UploadedFileName: string read FUploadedFileName write FUploadedFileName;
  end;

function UniMainModule: TUniMainModule;

implementation

{$R *.dfm}

uses
  UniGUIVars,
  JsonSchemaLoader,
  System.IOUtils;

function UniMainModule: TUniMainModule;
begin
  Result := TUniMainModule(UniApplication.UniMainModule);
end;

constructor TUniMainModule.Create(AOwner: TComponent);
var
  IniPath: string;
begin
  inherited;
  EnableSynchronousOperations := True;
  IniPath := TPath.Combine(ExtractFilePath(ParamStr(0)),
    'methyl-config-editor-web.ini');
  FSettings := TServerSettings.Create(IniPath);
  FCatalog := TSchemaCatalog.Create;
  TSchemaCatalog.SetCurrent(FCatalog);
  FDocument := TJsonDocumentModel.Create;
  ReloadCatalog;
end;

destructor TUniMainModule.Destroy;
begin
  FSchemaDoc.Free;
  FDocument.Free;
  FCatalog.Free;
  FSettings.Free;
  inherited;
end;

function TUniMainModule.CurrentSchemaPath(const SchemaIndex: Integer): string;
begin
  Result := '';
  if (SchemaIndex < 0) or (SchemaIndex >= FCatalog.Count) then
    Exit;
  Result := FCatalog.Entry(SchemaIndex).FilePath;
end;

procedure TUniMainModule.ReloadCatalog;
begin
  FCatalog.LoadFromRoot(FSettings.GetSchemasRoot);
end;

procedure TUniMainModule.LoadSelectedSchema(const SchemaPath: string);
var
  Loader: TJsonSchemaLoader;
begin
  FSchemaDoc.Free;
  FSchemaDoc := nil;
  if SchemaPath = '' then
    Exit;
  Loader := TJsonSchemaLoader.Create;
  try
    FSchemaDoc := Loader.LoadDocumentFromFile(SchemaPath);
  finally
    Loader.Free;
  end;
end;

function TUniMainModule.SchemaTitle: string;
begin
  Result := '';
  if Assigned(FSchemaDoc) and Assigned(FSchemaDoc.Root) then
    Result := FSchemaDoc.Root.Title;
end;

initialization
  RegisterMainModuleClass(TUniMainModule);

end.
