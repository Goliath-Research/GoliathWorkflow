unit MainForm;

interface

uses
  Winapi.Windows,
  System.Classes,
  System.JSON,
  System.SysUtils,
  uniGUIForm,
  uniGUIApplication,
  uniGUITypes,
  uniGUIVars,
  uniGUIAbstractClasses,
  uniPanel,
  uniComboBox,
  uniLabel,
  uniMemo,
  uniButton,
  uniFileUpload,
  SchemaNode,
  SchemaDefaults, uniGUIBaseClasses, uniGUIClasses, uniMultiItem, Vcl.Controls,
  Vcl.Forms;

type
  TUniMainForm = class(TUniForm)
    PanelTop: TUniPanel;
    lblSchema: TUniLabel;
    cboSchema: TUniComboBox;
    lblSchemasRoot: TUniLabel;
    lblSchemasRootValue: TUniLabel;
    btnNewJson: TUniButton;
    btnEditJson: TUniButton;
    btnDownloadJson: TUniButton;
    UploadJson: TUniFileUpload;
    MemoJson: TUniMemo;
    procedure UniFormCreate(Sender: TObject);
    procedure cboSchemaChange(Sender: TObject);
    procedure btnNewJsonClick(Sender: TObject);
    procedure btnEditJsonClick(Sender: TObject);
    procedure btnDownloadJsonClick(Sender: TObject);
    procedure UploadJsonCompleted(Sender: TObject; AStream: TFileStream);
  private
    procedure ReloadCatalog;
    procedure LoadSelectedSchema;
    procedure RefreshMemo;
    function EnsureSchemaSelected: Boolean;
    function SchemaTitle: string;
    function CurrentSchemaIndex: Integer;
  public
  end;

function UniMainForm: TUniMainForm;

implementation

{$R *.dfm}

uses
  MainModule,
  System.IOUtils,
  SchemaEditorService;

function UniMainForm: TUniMainForm;
begin
  Result := TUniMainForm(UniMainModule.GetFormInstance(TUniMainForm));
end;

procedure TUniMainForm.UniFormCreate(Sender: TObject);
begin
  lblSchemasRootValue.Caption := UniMainModule.Settings.GetSchemasRoot;
  ReloadCatalog;
end;

function TUniMainForm.CurrentSchemaIndex: Integer;
begin
  Result := cboSchema.ItemIndex;
end;

function TUniMainForm.SchemaTitle: string;
var
  Title: string;
  Path: string;
begin
  Title := UniMainModule.SchemaTitle;
  if Title <> '' then
    Exit(Title);
  Path := UniMainModule.CurrentSchemaPath(CurrentSchemaIndex);
  if Path <> '' then
    Exit(TPath.GetFileNameWithoutExtension(Path));
  Result := 'JSON Value';
end;

function TUniMainForm.EnsureSchemaSelected: Boolean;
begin
  Result := Assigned(UniMainModule.SchemaDoc) and
    Assigned(UniMainModule.SchemaDoc.Root);
  if not Result then
    MessageDlg('Select a JSON schema first.', mtInformation, [mbOK]);
end;

procedure TUniMainForm.ReloadCatalog;
var
  I: Integer;
begin
  UniMainModule.ReloadCatalog;
  cboSchema.Items.Clear;
  for I := 0 to UniMainModule.Catalog.Count - 1 do
    cboSchema.Items.Add(UniMainModule.Catalog.Entry(I).DisplayName);
  if cboSchema.Items.Count > 0 then
    cboSchema.ItemIndex := 0;
  LoadSelectedSchema;
end;

procedure TUniMainForm.LoadSelectedSchema;
var
  Path: string;
begin
  Path := UniMainModule.CurrentSchemaPath(CurrentSchemaIndex);
  UniMainModule.LoadSelectedSchema(Path);
end;

procedure TUniMainForm.RefreshMemo;
begin
  MemoJson.Lines.Text := UniMainModule.Document.ToJsonText(True);
end;

procedure TUniMainForm.cboSchemaChange(Sender: TObject);
begin
  LoadSelectedSchema;
end;

procedure TUniMainForm.btnNewJsonClick(Sender: TObject);
begin
  if not EnsureSchemaSelected then
    Exit;
  UniMainModule.Document.SetRoot(
    TSchemaDefaults.CreateDefaultValue(UniMainModule.SchemaDoc.Root), True);
  UniMainModule.HasJsonValue := True;
  UniMainModule.UploadedFileName := '';
  RefreshMemo;
  btnEditJsonClick(Sender);
end;

procedure TUniMainForm.btnEditJsonClick(Sender: TObject);
var
  Title: string;
  EditedValue: TJSONValue;
begin
  if not EnsureSchemaSelected then
    Exit;
  if not UniMainModule.HasJsonValue then
  begin
    MessageDlg('Upload a JSON file or create a new document first.', mtInformation,
      [mbOK]);
    Exit;
  end;
  Title := SchemaTitle;
  if TSchemaEditorService.EditRootValue(Title, UniMainModule.SchemaDoc.Root,
    UniMainModule.Document.Root, EditedValue) then
  begin
    UniMainModule.Document.SetRoot(EditedValue, True);
    UniMainModule.HasJsonValue := True;
    RefreshMemo;
  end;
end;

procedure TUniMainForm.UploadJsonCompleted(Sender: TObject; AStream: TFileStream);
var
  Text: string;
  Bytes: TBytes;
begin
  SetLength(Bytes, AStream.Size);
  AStream.Position := 0;
  AStream.ReadBuffer(Bytes[0], AStream.Size);
  Text := TEncoding.UTF8.GetString(Bytes);
  try
    UniMainModule.Document.LoadFromString(Text);
    UniMainModule.HasJsonValue := True;
    UniMainModule.UploadedFileName := UploadJson.FileName;
    RefreshMemo;
  except
    on E: Exception do
      MessageDlg('Failed to load JSON: ' + E.Message, mtError, [mbOK]);
  end;
end;

procedure TUniMainForm.btnDownloadJsonClick(Sender: TObject);
var
  TempPath: string;
  FileName: string;
begin
  if not UniMainModule.HasJsonValue then
  begin
    if not EnsureSchemaSelected then
      Exit;
    UniMainModule.Document.SetRoot(
      TSchemaDefaults.CreateDefaultValue(UniMainModule.SchemaDoc.Root), True);
    UniMainModule.HasJsonValue := True;
  end;
  FileName := UniMainModule.UploadedFileName;
  if FileName = '' then
    FileName := SchemaTitle + '.json';
  TempPath := TPath.Combine(TPath.GetTempPath,
    'methyl-config-' + IntToStr(GetTickCount) + '-' + FileName);
  UniMainModule.Document.SaveToFile(TempPath);
  UniSession.SendFile(TempPath, FileName);
end;

initialization
  RegisterAppFormClass(TUniMainForm);

end.
