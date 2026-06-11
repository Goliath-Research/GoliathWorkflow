unit RemoteSchemaCatalog;

{
  Fetches workflow action JSON Schemas from the MethylPipeline REST gateway
  (GET /v1/actions, GET /v1/actions/{name}/schema) and merges them into
  TSchemaCatalog as remote:// entries for the schema dropdown.
}

interface

uses
  SchemaCatalog;

type
  TRemoteSchemaCatalog = class
  private
    class function NormalizeBaseUrl(const BaseUrl: string): string; static;
    class procedure FetchSchema(const Client: TObject; const BaseUrl, ActionName,
      Direction: string; ACatalog: TSchemaCatalog); static;
  public
    class procedure MergeInto(ACatalog: TSchemaCatalog; const BaseUrl: string);
  end;

implementation

uses
  System.Classes,
  System.JSON,
  System.Net.HttpClient,
  System.NetEncoding,
  System.SysUtils;

class function TRemoteSchemaCatalog.NormalizeBaseUrl(const BaseUrl: string): string;
begin
  Result := Trim(BaseUrl);
  while Result.EndsWith('/') do
    SetLength(Result, Length(Result) - 1);
end;

class procedure TRemoteSchemaCatalog.FetchSchema(const Client: TObject;
  const BaseUrl, ActionName, Direction: string; ACatalog: TSchemaCatalog);
var
  Http: THTTPClient;
  Resp: IHTTPResponse;
  Url, DisplayName, VirtualPath, SchemaText: string;
  Root, SchemaVal: TJSONValue;
  SchemaObj: TJSONObject;
begin
  Http := THTTPClient(Client);
  Url := Format('%s/actions/%s/schema?direction=%s',
    [BaseUrl, TNetEncoding.URL.Encode(ActionName), Direction]);
  Resp := Http.Get(Url);
  if Resp.StatusCode <> 200 then
    Exit;
  Root := TJSONObject.ParseJSONValue(Resp.ContentAsString(TEncoding.UTF8));
  if not (Root is TJSONObject) then
  begin
    Root.Free;
    Exit;
  end;
  try
    SchemaVal := TJSONObject(Root).GetValue('schema_json');
    if not Assigned(SchemaVal) then
      Exit;
    SchemaText := SchemaVal.ToJSON;
    DisplayName := Format('action: %s (%s)', [ActionName, Direction]);
    VirtualPath := Format('remote://%s/%s', [ActionName, Direction]);
    ACatalog.RegisterRemoteEntry(DisplayName, VirtualPath, SchemaText);
  finally
    Root.Free;
  end;
end;

class procedure TRemoteSchemaCatalog.MergeInto(ACatalog: TSchemaCatalog;
  const BaseUrl: string);
var
  Http: THTTPClient;
  Resp: IHTTPResponse;
  Root, ActionsVal, ItemVal: TJSONValue;
  ActionsArr: TJSONArray;
  Item: TJSONObject;
  I: Integer;
  ActionName: string;
  HasInput, HasOutput: Boolean;
  Normalized: string;
begin
  if (ACatalog = nil) or Trim(BaseUrl) = '' then
    Exit;
  Normalized := NormalizeBaseUrl(BaseUrl);
  Http := THTTPClient.Create;
  try
    Http.ConnectionTimeout := 5000;
    Http.ResponseTimeout := 15000;
    Resp := Http.Get(Normalized + '/actions');
    if Resp.StatusCode <> 200 then
      Exit;
    Root := TJSONObject.ParseJSONValue(Resp.ContentAsString(TEncoding.UTF8));
    if not (Root is TJSONObject) then
    begin
      Root.Free;
      Exit;
    end;
    try
      ActionsVal := TJSONObject(Root).GetValue('actions');
      if not (ActionsVal is TJSONArray) then
        Exit;
      ActionsArr := TJSONArray(ActionsVal);
      for I := 0 to ActionsArr.Count - 1 do
      begin
        ItemVal := ActionsArr.Items[I];
        if not (ItemVal is TJSONObject) then
          Continue;
        Item := TJSONObject(ItemVal);
        if Item.GetValue('action_name') = nil then
          Continue;
        ActionName := Item.GetValue('action_name').Value;
        HasInput := False;
        HasOutput := False;
        if Item.GetValue('has_input_schema') is TJSONTrue then
          HasInput := True;
        if Item.GetValue('has_output_schema') is TJSONTrue then
          HasOutput := True;
        if HasInput then
          FetchSchema(Http, Normalized, ActionName, 'input', ACatalog);
        if HasOutput then
          FetchSchema(Http, Normalized, ActionName, 'output', ACatalog);
      end;
    finally
      Root.Free;
    end;
  finally
    Http.Free;
  end;
end;

end.
