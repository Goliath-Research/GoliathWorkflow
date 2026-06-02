unit JsonDocumentModel;

interface

uses
  System.JSON,
  System.SysUtils,
  JsonPath;

type
  TJsonDocumentModel = class
  private
    FRoot: TJSONValue;
    FOwnsRoot: Boolean;
  public
    constructor Create(AOwnsRoot: Boolean = True);
    destructor Destroy; override;
    procedure LoadFromFile(const Path: string);
    procedure LoadFromString(const JsonText: string);
    procedure SaveToFile(const Path: string);
    function ToJsonText(Pretty: Boolean = True): string;
    function CloneDocument: TJsonDocumentModel;
    function GetRootObject: TJSONObject;
    procedure SetRoot(AValue: TJSONValue; AOwns: Boolean = True);
    property Root: TJSONValue read FRoot;
  end;

implementation

uses
  System.Classes,
  System.IOUtils;

constructor TJsonDocumentModel.Create(AOwnsRoot: Boolean);
begin
  inherited Create;
  FOwnsRoot := AOwnsRoot;
  FRoot := TJSONObject.Create;
end;

destructor TJsonDocumentModel.Destroy;
begin
  if FOwnsRoot and Assigned(FRoot) then
    FRoot.Free;
  inherited Destroy;
end;

procedure TJsonDocumentModel.LoadFromFile(const Path: string);
begin
  LoadFromString(TFile.ReadAllText(Path, TEncoding.UTF8));
end;

procedure TJsonDocumentModel.LoadFromString(const JsonText: string);
var
  Parsed: TJSONValue;
begin
  Parsed := TJSONObject.ParseJSONValue(JsonText, False, True);
  if not Assigned(Parsed) then
    raise Exception.Create('Invalid JSON document');
  if FOwnsRoot and Assigned(FRoot) then
    FRoot.Free;
  FRoot := Parsed;
  FOwnsRoot := True;
end;

procedure TJsonDocumentModel.SaveToFile(const Path: string);
begin
  TFile.WriteAllText(Path, ToJsonText(True), TEncoding.UTF8);
end;

function TJsonDocumentModel.ToJsonText(Pretty: Boolean): string;
begin
  if not Assigned(FRoot) then
    Exit('{}');
  if Pretty then
    Result := FRoot.Format(2)
  else
    Result := FRoot.ToJSON;
end;

function TJsonDocumentModel.CloneDocument: TJsonDocumentModel;
begin
  Result := TJsonDocumentModel.Create(True);
  if Assigned(FRoot) then
    Result.FRoot := TJsonPath.CloneValue(FRoot);
end;

function TJsonDocumentModel.GetRootObject: TJSONObject;
begin
  if FRoot is TJSONObject then
    Result := TJSONObject(FRoot)
  else
  begin
    if FOwnsRoot and Assigned(FRoot) then
      FRoot.Free;
    FRoot := TJSONObject.Create;
    Result := TJSONObject(FRoot);
  end;
end;

procedure TJsonDocumentModel.SetRoot(AValue: TJSONValue; AOwns: Boolean);
begin
  if FOwnsRoot and Assigned(FRoot) then
    FRoot.Free;
  FRoot := AValue;
  FOwnsRoot := AOwns;
end;

end.
