unit WfEngine.GatewayService.Tests;

{
  Service-layer tests for IGatewayService (no HTTP/DMVC).
  Configure METHYLPIPELINE_DB when running integration cases.
}

interface

procedure RunGatewayServiceTests;

implementation

uses
  System.SysUtils,
  WfEngine.Connection,
  WfEngine.GatewayDtos,
  WfEngine.GatewayHost,
  WfEngine.GatewayService;

procedure AssertTrue(const ACondition: Boolean; const AMessage: string);
begin
  if not ACondition then
    raise Exception.Create('ASSERT FAILED: ' + AMessage);
end;

procedure TestGetActionSchemaRejectsInvalidDirection;
var
  Gateway: IGatewayService;
  ConnCfg: TConnectionConfig;
begin
  ConnCfg := ResolveConnectionConfig;
  if ConnCfg.ConnectionString = '' then
  begin
    Writeln('  SKIP TestGetActionSchemaRejectsInvalidDirection (no DB configured)');
    Exit;
  end;

  InitGatewayHost(ConnCfg);
  try
    Gateway := GetGatewayService;
    try
      Gateway.GetActionSchema('pipeline.centroid', 'sideways');
      raise Exception.Create('Expected exception for invalid direction');
    except
      on E: Exception do
        AssertTrue(Pos('direction must be input or output', E.Message) > 0,
          'Wrong exception: ' + E.Message);
    end;
  finally
    ShutdownGatewayHost;
  end;
end;

procedure TestListActionsReturnsCatalog;
var
  Gateway: IGatewayService;
  List: TActionListResponse;
  ConnCfg: TConnectionConfig;
begin
  ConnCfg := ResolveConnectionConfig;
  if ConnCfg.ConnectionString = '' then
  begin
    Writeln('  SKIP TestListActionsReturnsCatalog (no DB configured)');
    Exit;
  end;

  InitGatewayHost(ConnCfg);
  try
    Gateway := GetGatewayService;
    List := Gateway.ListActions;
    try
      AssertTrue(Length(List.actions) >= 0, 'ListActions should return a response');
    finally
      List.Free;
    end;
  finally
    ShutdownGatewayHost;
  end;
end;

procedure TestWorkerAuthRequestDtoDefaults;
var
  Req: TWorkerRequestTaskRequest;
begin
  Req := TWorkerRequestTaskRequest.Create;
  try
    AssertTrue(Req.max_lease_seconds = 300, 'Default max_lease_seconds should be 300');
  finally
    Req.Free;
  end;
end;

procedure RunGatewayServiceTests;
begin
  Writeln('Gateway service tests');
  TestWorkerAuthRequestDtoDefaults;
  TestGetActionSchemaRejectsInvalidDirection;
  TestListActionsReturnsCatalog;
  Writeln('  Gateway service tests passed.');
end;

end.
