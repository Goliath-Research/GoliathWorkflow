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
  SchemaNode,
  JsonSchemaLoader,
  JsonDocumentModel,
  SchemaDefaults;

type
  TMainForm = class(TForm)
    PanelTop: TPanel;
    lblSchema: TLabel;
    cboSchema: TComboBox;
    lblSchemasRoot: TLabel;
    edtSchemasRoot: TEdit;
    btnBrowseSchemas: TButton;
    btnEditJson: TButton;
    btnNewJson: TButton;
    MemoJson: TMemo;
    MainMenu: TMainMenu;
    mnuFile: TMenuItem;
    mnuNewJson: TMenuItem;
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
    procedure btnEditJsonClick(Sender: TObject);
    procedure cboSchemaChange(Sender: TObject);
    procedure mnuNewJsonClick(Sender: TObject);
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
    FHasJsonValue: Boolean;
    function CanUseRootValue(AValue: TJSONValue; ASchema: TSchemaNode): Boolean;
    function EditRootValue(const ATitle: string; ASchema: TSchemaNode;
      ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
    function EditWrappedRootValue(const ATitle: string; ASchema: TSchemaNode;
      ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
    function EnsureSchemaSelected: Boolean;
    function SchemaTitle: string;
    procedure CreateDefaultJsonValue;
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
  System.IOUtils,
  ArrayEditorForm,
  PropertyEditorForm,
  SchemaValueSummary;

{$R *.dfm}

procedure TMainForm.FormCreate(Sender: TObject);
begin
  FSettings := TAppSettings.Create(
    TPath.Combine(TPath.GetDirectoryName(ParamStr(0)), 'methyl-config-editor.ini'));
  FCatalog := TSchemaCatalog.Create;
  TSchemaCatalog.SetCurrent(FCatalog);
  FDocument := TJsonDocumentModel.Create;
  edtSchemasRoot.Text := FSettings.GetSchemasRoot;
  ReloadCatalog;
  if FSettings.GetLastDocumentPath <> '' then
  begin
    FDocumentPath := FSettings.GetLastDocumentPath;
    if TFile.Exists(FDocumentPath) then
    begin
      FDocument.LoadFromFile(FDocumentPath);
      FHasJsonValue := True;
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

function TMainForm.CanUseRootValue(AValue: TJSONValue; ASchema: TSchemaNode): Boolean;
begin
  Result := False;
  if not Assigned(AValue) or not Assigned(ASchema) then
    Exit;
  if TSchemaValueSummary.IsNullValue(AValue) then
    Exit(ASchema.Nullable or (ASchema.Kind = skNull));
  case ASchema.Kind of
    skNull:
      Result := AValue is TJSONNull;
    skBoolean:
      Result := (AValue is TJSONTrue) or (AValue is TJSONFalse);
    skInteger, skNumber:
      Result := AValue is TJSONNumber;
    skString:
      Result := AValue is TJSONString;
    skObject, skDictionary:
      Result := AValue is TJSONObject;
    skArray:
      Result := AValue is TJSONArray;
  else
    Result := True;
  end;
end;

procedure TMainForm.CreateDefaultJsonValue;
begin
  if not EnsureSchemaSelected then
    Exit;
  FDocument.SetRoot(TSchemaDefaults.CreateDefaultValue(FSchemaDoc.Root), True);
  FDocumentPath := '';
  FHasJsonValue := True;
  RefreshMemo;
end;

function TMainForm.EditRootValue(const ATitle: string; ASchema: TSchemaNode;
  ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
var
  Working: TJSONValue;
  WorkingObj: TJSONObject;
  WorkingArr: TJSONArray;
begin
  Result := False;
  AEditedValue := nil;
  if CanUseRootValue(ASourceValue, ASchema) then
    Working := ASourceValue.Clone as TJSONValue
  else
    Working := TSchemaDefaults.CreateDefaultValue(ASchema);
  try
    if TSchemaValueSummary.IsNullValue(Working) then
      Exit(EditWrappedRootValue(ATitle, ASchema, Working, AEditedValue));
    case ASchema.Kind of
      skObject:
        begin
          if Working is TJSONObject then
            WorkingObj := TJSONObject(Working)
          else
            WorkingObj := TSchemaDefaults.CreateDefaultObject(ASchema);
          try
            if TPropertyEditorForm.EditObject(Self, ATitle, ASchema, WorkingObj) then
            begin
              AEditedValue := WorkingObj.Clone as TJSONValue;
              Result := True;
            end;
          finally
            if WorkingObj <> Working then
              WorkingObj.Free;
          end;
        end;
      skDictionary:
        begin
          if Working is TJSONObject then
            WorkingObj := TJSONObject(Working)
          else
            WorkingObj := TJSONObject.Create;
          try
            if TPropertyEditorForm.EditObject(Self, ATitle, ASchema, WorkingObj) then
            begin
              AEditedValue := WorkingObj.Clone as TJSONValue;
              Result := True;
            end;
          finally
            if WorkingObj <> Working then
              WorkingObj.Free;
          end;
        end;
      skArray:
        begin
          if Working is TJSONArray then
            WorkingArr := TJSONArray(Working)
          else
            WorkingArr := TJSONArray.Create;
          try
            if TArrayEditorForm.EditArray(Self, ATitle, ASchema, WorkingArr) then
            begin
              AEditedValue := WorkingArr.Clone as TJSONValue;
              Result := True;
            end;
          finally
            if WorkingArr <> Working then
              WorkingArr.Free;
          end;
        end;
    else
      Result := EditWrappedRootValue(ATitle, ASchema, Working, AEditedValue);
    end;
  finally
    Working.Free;
  end;
end;

function TMainForm.EditWrappedRootValue(const ATitle: string; ASchema: TSchemaNode;
  ASourceValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
var
  WrapperSchema: TSchemaNode;
  WrapperObject: TJSONObject;
  Edited: TJSONValue;
begin
  Result := False;
  AEditedValue := nil;
  WrapperSchema := TSchemaNode.Create;
  WrapperObject := TJSONObject.Create;
  try
    WrapperSchema.Kind := skObject;
    WrapperSchema.Title := ATitle;
    WrapperSchema.AddProperty('value', ASchema);
    WrapperObject.AddPair('value', ASourceValue.Clone as TJSONValue);
    if TPropertyEditorForm.EditObject(Self, ATitle, WrapperSchema, WrapperObject) then
    begin
      Edited := WrapperObject.GetValue('value');
      if Assigned(Edited) then
        AEditedValue := Edited.Clone as TJSONValue
      else
        AEditedValue := TJSONNull.Create;
      Result := True;
    end;
  finally
    WrapperObject.Free;
    WrapperSchema.Free;
  end;
end;

function TMainForm.EnsureSchemaSelected: Boolean;
begin
  Result := Assigned(FSchemaDoc) and Assigned(FSchemaDoc.Root);
  if not Result then
    MessageDlg('Select a JSON schema first.', TMsgDlgType.mtInformation,
      [TMsgDlgBtn.mbOK], 0);
end;

function TMainForm.SchemaTitle: string;
begin
  Result := '';
  if Assigned(FSchemaDoc) and Assigned(FSchemaDoc.Root) then
    Result := FSchemaDoc.Root.Title;
  if Result = '' then
    Result := TPath.GetFileNameWithoutExtension(CurrentSchemaPath);
  if Result = '' then
    Result := 'JSON Value';
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

procedure TMainForm.btnEditJsonClick(Sender: TObject);
begin
  mnuEditPropertiesClick(Sender);
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
    FHasJsonValue := True;
    FSettings.SetLastDocumentPath(FDocumentPath);
    RefreshMemo;
  end;
end;

procedure TMainForm.mnuNewJsonClick(Sender: TObject);
begin
  if not EnsureSchemaSelected then
    Exit;
  CreateDefaultJsonValue;
  mnuEditPropertiesClick(Sender);
end;

procedure TMainForm.mnuSaveJsonClick(Sender: TObject);
var
  Path: string;
begin
  if not FHasJsonValue then
  begin
    if not EnsureSchemaSelected then
      Exit;
    CreateDefaultJsonValue;
  end;
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
  Title: string;
  EditedValue: TJSONValue;
begin
  if not EnsureSchemaSelected then
    Exit;
  if not FHasJsonValue then
  begin
    mnuOpenJsonClick(Sender);
    if not FHasJsonValue then
      Exit;
  end;
  Title := SchemaTitle;
  if EditRootValue(Title, FSchemaDoc.Root, FDocument.Root, EditedValue) then
  begin
    FDocument.SetRoot(EditedValue, True);
    FHasJsonValue := True;
    RefreshMemo;
  end;
end;

procedure TMainForm.mnuReloadCatalogClick(Sender: TObject);
begin
  ReloadCatalog;
end;

end.
