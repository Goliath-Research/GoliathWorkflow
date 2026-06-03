unit MainForm;

interface

uses
  Winapi.Windows,
  Winapi.Messages,
  System.SysUtils,
  System.Classes,
  Vcl.Graphics,
  Vcl.Controls,
  Vcl.Forms,
  Vcl.Dialogs,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  Vcl.Menus,
  System.JSON,
  AppSettings,
  SchemaCatalog,
  SchemaDocument,
  JsonSchemaLoader,
  JsonDocumentModel,
  SchemaDefaults,
  PropertyEditorForm;

type
  TMainForm = class(TForm)
    PanelTop: TPanel;
    lblSchema: TLabel;
    cboSchema: TComboBox;
    lblSchemasRoot: TLabel;
    edtSchemasRoot: TEdit;
    btnBrowseSchemas: TButton;
    MemoJson: TMemo;
    MainMenu: TMainMenu;
    mnuFile: TMenuItem;
    mnuOpenJson: TMenuItem;
    mnuSaveJson: TMenuItem;
    mnuSep1: TMenuItem;
    mnuExit: TMenuItem;
    mnuEdit: TMenuItem;
    mnuEditProperties: TMenuItem;
    mnuReloadCatalog: TMenuItem;
    OpenDialogJson: TOpenDialog;
    SaveDialogJson: TSaveDialog;
    FileOpenDialog: TFileOpenDialog;
    procedure FormCreate(Sender: TObject);
    procedure FormDestroy(Sender: TObject);
    procedure btnBrowseSchemasClick(Sender: TObject);
    procedure cboSchemaChange(Sender: TObject);
    procedure mnuOpenJsonClick(Sender: TObject);
    procedure mnuSaveJsonClick(Sender: TObject);
    procedure mnuExitClick(Sender: TObject);
    procedure mnuEditPropertiesClick(Sender: TObject);
    procedure mnuReloadCatalogClick(Sender: TObject);
  private
    FSettings: TAppSettings;
    FCatalog: TSchemaCatalog;
    FSchemaDoc: TSchemaDocument;
    FDocument: TJsonDocumentModel;
    FDocumentPath: string;
    procedure ReloadCatalog;
    procedure LoadSelectedSchema;
    procedure RefreshMemo;
    function CurrentSchemaPath: string;
  public
  end;

var
  MainFormInstance: TMainForm;

implementation

uses
  System.UITypes,
  System.IOUtils;

{$R *.dfm}

procedure TMainForm.FormCreate(Sender: TObject);
begin
  FSettings := TAppSettings.Create(
    TPath.Combine(TPath.GetDirectoryName(ParamStr(0)), 'methyl-config-editor.ini'));
  FCatalog := TSchemaCatalog.Create;
  FDocument := TJsonDocumentModel.Create;
  edtSchemasRoot.Text := FSettings.GetSchemasRoot;
  ReloadCatalog;
  if FSettings.GetLastDocumentPath <> '' then
  begin
    FDocumentPath := FSettings.GetLastDocumentPath;
    if TFile.Exists(FDocumentPath) then
    begin
      FDocument.LoadFromFile(FDocumentPath);
      RefreshMemo;
    end;
  end;
end;

procedure TMainForm.FormDestroy(Sender: TObject);
begin
  FSchemaDoc.Free;
  FDocument.Free;
  FCatalog.Free;
  FSettings.Free;
end;

function TMainForm.CurrentSchemaPath: string;
var
  Idx: Integer;
begin
  Idx := cboSchema.ItemIndex;
  if Idx < 0 then
    Exit('');
  Result := FCatalog.Entry(Idx).FilePath;
end;

procedure TMainForm.ReloadCatalog;
var
  I: Integer;
  LastPath: string;
  Idx: Integer;
begin
  FSettings.SetSchemasRoot(edtSchemasRoot.Text);
  FCatalog.LoadFromRoot(edtSchemasRoot.Text);
  cboSchema.Items.Clear;
  for I := 0 to FCatalog.Count - 1 do
    cboSchema.Items.Add(FCatalog.Entry(I).DisplayName);
  LastPath := FSettings.GetLastSchemaPath;
  Idx := FCatalog.FindByPath(LastPath);
  if Idx >= 0 then
    cboSchema.ItemIndex := Idx
  else if cboSchema.Items.Count > 0 then
    cboSchema.ItemIndex := 0;
  LoadSelectedSchema;
end;

procedure TMainForm.LoadSelectedSchema;
var
  Path: string;
  Loader: TJsonSchemaLoader;
begin
  FSchemaDoc.Free;
  FSchemaDoc := nil;
  Path := CurrentSchemaPath;
  if Path = '' then
    Exit;
  Loader := TJsonSchemaLoader.Create;
  try
    FSchemaDoc := Loader.LoadDocumentFromFile(Path);
    FSettings.SetLastSchemaPath(Path);
  finally
    Loader.Free;
  end;
end;

procedure TMainForm.RefreshMemo;
begin
  MemoJson.Lines.Text := FDocument.ToJsonText(True);
end;

procedure TMainForm.btnBrowseSchemasClick(Sender: TObject);
begin
  FileOpenDialog.Title := 'Select schemas/config directory';
  FileOpenDialog.Options := [fdoPickFolders];
  if FileOpenDialog.Execute then
  begin
    edtSchemasRoot.Text := FileOpenDialog.FileName;
    ReloadCatalog;
  end;
end;

procedure TMainForm.cboSchemaChange(Sender: TObject);
begin
  LoadSelectedSchema;
end;

procedure TMainForm.mnuOpenJsonClick(Sender: TObject);
begin
  if OpenDialogJson.Execute then
  begin
    FDocumentPath := OpenDialogJson.FileName;
    FDocument.LoadFromFile(FDocumentPath);
    FSettings.SetLastDocumentPath(FDocumentPath);
    RefreshMemo;
  end;
end;

procedure TMainForm.mnuSaveJsonClick(Sender: TObject);
var
  Path: string;
begin
  Path := FDocumentPath;
  if Path = '' then
  begin
    if not SaveDialogJson.Execute then
      Exit;
    Path := SaveDialogJson.FileName;
  end;
  FDocument.SaveToFile(Path);
  FDocumentPath := Path;
  FSettings.SetLastDocumentPath(Path);
  RefreshMemo;
end;

procedure TMainForm.mnuExitClick(Sender: TObject);
begin
  Close;
end;

procedure TMainForm.mnuEditPropertiesClick(Sender: TObject);
var
  RootObj: TJSONObject;
  Title: string;
begin
  if not Assigned(FSchemaDoc) or not Assigned(FSchemaDoc.Root) then
  begin
    MessageDlg('Select a JSON schema first.', TMsgDlgType.mtInformation, [TMsgDlgBtn.mbOK], 0);
    Exit;
  end;
  RootObj := FDocument.GetRootObject;
  if RootObj.Count = 0 then
  begin
    RootObj := TSchemaDefaults.CreateDefaultObject(FSchemaDoc.Root);
    FDocument.SetRoot(RootObj, True);
  end;
  Title := FSchemaDoc.Root.Title;
  if Title = '' then
    Title := TPath.GetFileNameWithoutExtension(CurrentSchemaPath);
  if TPropertyEditorForm.EditObject(Self, Title, FSchemaDoc.Root, RootObj) then
    RefreshMemo;
end;

procedure TMainForm.mnuReloadCatalogClick(Sender: TObject);
begin
  ReloadCatalog;
end;

end.
