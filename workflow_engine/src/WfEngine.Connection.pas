unit WfEngine.Connection;

{
  UniDAC connection configuration for the workflow gateway.

  Resolves settings from environment variables (and optional explicit overrides).
  Production deployments should set WF_USE_MANAGED_IDENTITY=1 for Azure Entra ID
  token auth via the VM/ARC IMDS endpoint; local dev may use a plain connection string.
}

interface

uses
  Uni;

type
  TDatabaseBackend = (dbMssql, dbPostgres);

  TConnectionConfig = record
    Backend: TDatabaseBackend;
    ConnectionString: string;
    SchemaName: string;
    UseManagedIdentity: Boolean;
    function SchemaDot: string;
  end;

function GetDatabaseBackend: TDatabaseBackend;
function ResolveSchemaName: string;
function WfSchema: string;
function WfSchemaDot: string;
function BuildConnectionStringFromEnv: string;
function ResolveConnectionConfig(const AConnectionStringOverride: string = ''): TConnectionConfig;
procedure ConfigureUniConnection(AConn: TUniConnection; const AConfig: TConnectionConfig);
procedure ConnectUniDatabase(AConn: TUniConnection; const AConfig: TConnectionConfig);

implementation

uses
  System.SysUtils,
  System.StrUtils,
  System.Net.HttpClient,
  System.Net.URLClient,
  System.NetEncoding,
  System.JSON;

function GetEnvVar(const Name: string): string;
begin
  Result := GetEnvironmentVariable(Name);
end;

function EnvFlagTrue(const Name: string): Boolean;
var
  V: string;
begin
  V := LowerCase(Trim(GetEnvVar(Name)));
  Result := (V = '1') or (V = 'true') or (V = 'yes');
end;

function GetDatabaseBackend: TDatabaseBackend;
var
  V: string;
begin
  V := LowerCase(Trim(GetEnvVar('BACKEND_DB')));
  if (V = 'postgres') or (V = 'postgresql') or (V = 'pg') then
    Result := dbPostgres
  else
    Result := dbMssql;
end;

function ResolveSchemaName: string;
begin
  Result := Trim(GetEnvVar('WF_SCHEMA'));
  if Result = '' then
    Result := 'wf';
end;

function WfSchema: string;
begin
  Result := ResolveSchemaName;
end;

function WfSchemaDot: string;
begin
  Result := ResolveSchemaName + '.';
end;

function TConnectionConfig.SchemaDot: string;
begin
  if SchemaName = '' then
    Result := 'wf.'
  else
    Result := SchemaName + '.';
end;

function BuildConnectionStringFromEnv: string;
var
  MethylDb, AzureServer, AzureDb: string;
  PgHost, PgPort, PgDb, PgUser, PgPass: string;
begin
  MethylDb := GetEnvVar('METHYLPIPELINE_DB');
  if MethylDb <> '' then
    Exit(MethylDb);

  if GetDatabaseBackend = dbPostgres then
  begin
    PgHost := GetEnvVar('POSTGRES_HOST');
    if PgHost = '' then
      PgHost := 'localhost';
    PgPort := GetEnvVar('POSTGRES_PORT');
    if PgPort = '' then
      PgPort := '5432';
    PgDb := GetEnvVar('POSTGRES_DB');
    if PgDb = '' then
      PgDb := 'methylpipeline';
    PgUser := GetEnvVar('POSTGRES_USER');
    if PgUser = '' then
      PgUser := 'postgres';
    PgPass := GetEnvVar('POSTGRES_PASSWORD');
    Result := Format(
      'Provider Name=PostgreSQL;Data Source=%s;Port=%s;Database=%s;User ID=%s;Password=%s;',
      [PgHost, PgPort, PgDb, PgUser, PgPass]);
    Exit;
  end;

  AzureServer := GetEnvVar('AZURE_SQL_SERVER');
  AzureDb := GetEnvVar('AZURE_SQL_DB');
  if (AzureServer <> '') and (AzureDb <> '') then
  begin
    Result := Format('Server=tcp:%s,1433;Database=%s;Encrypt=True', [AzureServer, AzureDb]);
    Exit;
  end;

  Result := 'Provider Name=SQL Server;Data Source=localhost;Initial Catalog=MethylPipeline;Integrated Security=True';
end;

function ResolveUseManagedIdentity: Boolean;
begin
  Result := EnvFlagTrue('WF_USE_MANAGED_IDENTITY');
end;

function ResolveConnectionConfig(const AConnectionStringOverride: string): TConnectionConfig;
begin
  Result.Backend := GetDatabaseBackend;
  Result.SchemaName := ResolveSchemaName;
  Result.UseManagedIdentity := ResolveUseManagedIdentity;
  if AConnectionStringOverride <> '' then
    Result.ConnectionString := AConnectionStringOverride
  else
  begin
    Result.ConnectionString := GetEnvVar('METHYLPIPELINE_DB');
    if Result.ConnectionString = '' then
      Result.ConnectionString := BuildConnectionStringFromEnv;
  end;
end;

function GetEntraTokenResource(const ABackend: TDatabaseBackend): string;
begin
  if ABackend = dbPostgres then
    Result := 'https://ossrdbms-aad.database.windows.net'
  else
    Result := 'https://database.windows.net/';
end;

procedure ConfigureUniProvider(AConn: TUniConnection; const ABackend: TDatabaseBackend;
  const ASchemaName: string);
begin
  if AConn = nil then
    Exit;
  case ABackend of
    dbPostgres:
      begin
        AConn.ProviderName := 'PostgreSQL';
        AConn.SpecificOptions.Values['Schema'] := ASchemaName;
      end;
    dbMssql:
      AConn.ProviderName := 'SQL Server';
  end;
end;

function GetAccessTokenFromIMDS(out AToken: string; out AError: string;
  const AResource: string): Boolean;
var
  Client: THTTPClient;
  Url: string;
  Resp: IHTTPResponse;
  Body: string;
  JsonVal: TJSONValue;
  JsonObj: TJSONObject;
  EncRes: string;
begin
  AToken := '';
  AError := '';
  try
    Client := THTTPClient.Create;
    try
      Client.CustomHeaders['Metadata'] := 'true';
      EncRes := TNetEncoding.URL.Encode(AResource);
      Url := Format(
        'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=%s',
        [EncRes]);
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
          Exit(True)
        else if JsonObj.TryGetValue<string>('error_description', AError) then
          Exit(False)
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

function TryApplyManagedIdentityToConnection(AConn: TUniConnection; out AError: string;
  const ABackend: TDatabaseBackend): Boolean;
var
  Token: string;
  ConnStr: string;
  LowerStr: string;
  AtPos, SemPos: Integer;
  Resource: string;
begin
  AError := '';
  if AConn = nil then
  begin
    AError := 'AConn is nil';
    Exit(False);
  end;

  Resource := GetEntraTokenResource(ABackend);
  if not GetAccessTokenFromIMDS(Token, AError, Resource) then
    Exit(False);

  try
    ConnStr := AConn.ConnectString;
    LowerStr := LowerCase(ConnStr);
    if (ConnStr <> '') and not ConnStr.EndsWith(';') then
      ConnStr := ConnStr + ';';
    AtPos := Pos('accesstoken=', LowerStr);
    if AtPos > 0 then
    begin
      SemPos := PosEx(';', ConnStr, AtPos);
      if SemPos = 0 then
        SemPos := Length(ConnStr) + 1;
      ConnStr := Copy(ConnStr, 1, AtPos - 1) + 'AccessToken=' + Token + ';' +
        Copy(ConnStr, SemPos + 1, Length(ConnStr) - SemPos);
    end
    else if Pos('authentication=', LowerStr) > 0 then
      ConnStr := ConnStr + 'AccessToken=' + Token + ';'
    else
      ConnStr := ConnStr + 'Authentication=ActiveDirectoryAccessToken;AccessToken=' + Token + ';Encrypt=True';
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

procedure ConfigureUniConnection(AConn: TUniConnection; const AConfig: TConnectionConfig);
begin
  if AConn = nil then
    raise Exception.Create('ConfigureUniConnection: AConn is nil');
  ConfigureUniProvider(AConn, AConfig.Backend, AConfig.SchemaName);
  AConn.ConnectString := AConfig.ConnectionString;
end;

procedure ConnectUniDatabase(AConn: TUniConnection; const AConfig: TConnectionConfig);
var
  MiError: string;
begin
  if (AConn <> nil) and AConn.Connected then
    Exit;
  ConfigureUniConnection(AConn, AConfig);
  if AConfig.UseManagedIdentity then
  begin
    if not TryApplyManagedIdentityToConnection(AConn, MiError, AConfig.Backend) then
      raise Exception.Create('Managed identity connection failed: ' + MiError);
  end;
  AConn.Connect;
end;

end.
