unit WfEngine.DbAuth;

{
  DB auth helper for the workflow engine.

  - BuildConnectionStringFromEnv: resolves a connection string from env vars.
  - TryApplyManagedIdentityToConnection: retrieves an access token from the IMDS endpoint
    and applies it to a TUniConnection instance (UniDAC). UniDAC driver parameters may vary
    by version; adjust param names if necessary.
}

interface

uses
  System.SysUtils, Uni;

function BuildConnectionStringFromEnv: string;

// Attempts to obtain an Azure AD access token from the local IMDS endpoint and apply it
// to the provided TUniConnection. Returns True on success. On failure, returns False and
// returns an error message in AError.
function TryApplyManagedIdentityToConnection(AConn: TUniConnection; out AError: string; const AResource: string = 'https://database.windows.net/'): Boolean;

implementation

uses
  System.Net.HttpClient, System.Net.URLClient, System.NetEncoding, System.JSON, System.StrUtils;

function GetEnvVar(const Name: string): string;
begin
  Result := GetEnvironmentVariable(Name);
end;

function BuildConnectionStringFromEnv: string;
var
  methylDb, azureServer, azureDb: string;
begin
  methylDb := GetEnvVar('METHYLPIPELINE_DB');
  if methylDb <> '' then
    Exit(methylDb);

  azureServer := GetEnvVar('AZURE_SQL_SERVER');
  azureDb := GetEnvVar('AZURE_SQL_DB');
  if (azureServer <> '') and (azureDb <> '') then
  begin
    // Use Authentication=ActiveDirectoryAccessToken when supplying an access token
    Result := Format('Server=tcp:%s,1433;Database=%s;Encrypt=True', [azureServer, azureDb]);
    Exit;
  end;

  // Default fallback (adjust as needed)
  Result := 'Provider Name=SQL Server;Data Source=localhost;Initial Catalog=MethylPipeline;Integrated Security=True';
end;

function GetAccessTokenFromIMDS(out AToken: string; out AError: string; const AResource: string = 'https://database.windows.net/'): Boolean;
var
  Client: THTTPClient;
  Url: string;
  Resp: IHTTPResponse;
  Body: string;
  JsonVal: TJSONValue;
  JsonObj: TJSONObject;
  EncRes: string;
begin
  Result := False;
  AToken := '';
  AError := '';
  try
    Client := THTTPClient.Create;
    try
      Client.CustomHeaders['Metadata'] := 'true';
      EncRes := TNetEncoding.URL.Encode(AResource);
      Url := Format('http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=%s', [EncRes]);
      Resp := Client.Get(Url);
      if (Resp = nil) or (Resp.StatusCode <> 200) then
      begin
        AError := Format('IMDS request failed: %d %s', [Resp.StatusCode, Resp.StatusText]);
        Exit(False);
      end;
      Body := Resp.ContentAsString(TEncoding.UTF8);
      JsonVal := TJSONObject.ParseJSONValue(Body);
      if not (JsonVal is TJSONObject) then
      begin
        AError := 'IMDS response not JSON';
        Exit(False);
      end;
      JsonObj := TJSONObject(JsonVal);
      try
        if JsonObj.TryGetValue<string>('access_token', AToken) then
        begin
          Result := True;
          Exit(True);
        end
        else if JsonObj.TryGetValue<string>('error_description', AError) then
        begin
          Exit(False);
        end
        else
        begin
          AError := 'access_token not present in IMDS response';
          Exit(False);
        end;
      finally
        JsonObj.Free;
      end;
    finally
      Client.Free;
    end;
  except
    on E: Exception do
    begin
      AError := 'IMDS access token error: ' + E.ClassName + ': ' + E.Message;
      Result := False;
    end;
  end;
end;

function TryApplyManagedIdentityToConnection(AConn: TUniConnection; out AError: string; const AResource: string): Boolean;
var
  Token: string;
  ConnStr: string;
  LowerStr: string;
  AtPos, SemPos: Integer;
begin
  Result := False;
  AError := '';
  if AConn = nil then
  begin
    AError := 'AConn is nil';
    Exit(False);
  end;

  if not GetAccessTokenFromIMDS(Token, AError, AResource) then
    Exit(False);

  try
    ConnStr := AConn.ConnectString;
    LowerStr := LowerCase(ConnStr);
    if (ConnStr <> '') and not ConnStr.EndsWith(';') then
      ConnStr := ConnStr + ';';
    // If AccessToken already present, replace its value; else append appropriately.
    AtPos := Pos('accesstoken=', LowerStr);
    if AtPos > 0 then
    begin
      SemPos := PosEx(';', ConnStr, AtPos);
      if SemPos = 0 then
        SemPos := Length(ConnStr) + 1;
      ConnStr := Copy(ConnStr, 1, AtPos - 1) + 'AccessToken=' + Token + ';' + Copy(ConnStr, SemPos + 1, Length(ConnStr) - SemPos);
    end
    else if Pos('authentication=', LowerStr) > 0 then
    begin
      ConnStr := ConnStr + 'AccessToken=' + Token + ';';
    end
    else
    begin
      ConnStr := ConnStr + 'Authentication=ActiveDirectoryAccessToken;AccessToken=' + Token + ';Encrypt=True';
    end;
    AConn.ConnectString := ConnStr;

    Result := True;
  except
    on E: Exception do
    begin
      AError := 'Failed to apply access token to connect string: ' + E.ClassName + ': ' + E.Message;
      Result := False;
    end;
  end;
end;

end.
