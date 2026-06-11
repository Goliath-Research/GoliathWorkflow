program MethylConfigEditorWeb;

uses
  Forms,
  ServerModule in 'src\Web\ServerModule.pas' {UniServerModule: TUniGUIServerModule},
  MainModule in 'src\Web\MainModule.pas' {UniMainModule: TUniGUIMainModule},
  MainForm in 'src\Web\MainForm.pas' {UniMainForm: TUniMainForm},
  ServerSettings in 'src\Web\ServerSettings.pas',
  SchemaCatalog in 'src\App\SchemaCatalog.pas',
  JsonSchemaLoader in 'src\Schema\JsonSchemaLoader.pas',
  SchemaDocumentCache in 'src\Schema\SchemaDocumentCache.pas',
  SchemaNode in 'src\Schema\SchemaNode.pas',
  SchemaDocument in 'src\Schema\SchemaDocument.pas',
  SchemaDefaults in 'src\Schema\SchemaDefaults.pas',
  SchemaBranchResolver in 'src\Schema\SchemaBranchResolver.pas',
  SchemaDictionaryResolver in 'src\Schema\SchemaDictionaryResolver.pas',
  SchemaValidator in 'src\Schema\SchemaValidator.pas',
  RemoteSchemaCatalog in 'src\Schema\RemoteSchemaCatalog.pas',
  JsonPath in 'src\Data\JsonPath.pas',
  JsonArrayOps in 'src\Data\JsonArrayOps.pas',
  JsonDocumentModel in 'src\Data\JsonDocumentModel.pas',
  SchemaValueSummary in 'src\UI\SchemaValueSummary.pas',
  JsonValueParsing in 'src\Core\JsonValueParsing.pas',
  SchemaPropertyGrid in 'src\Web\SchemaPropertyGrid.pas',
  SchemaEditorService in 'src\Web\SchemaEditorService.pas',
  NestedEditorForm in 'src\Web\NestedEditorForm.pas' {UniNestedEditorForm: TUniForm},
  WebArrayEditorForm in 'src\Web\WebArrayEditorForm.pas' {UniWebArrayEditorForm: TUniForm};

{$R *.res}

begin
  ReportMemoryLeaksOnShutdown := True;
  Application.Initialize;
  TUniServerModule.Create(Application);
  Application.Run;
end.
