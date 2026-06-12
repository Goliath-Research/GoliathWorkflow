program WfEngineTests;

{$APPTYPE CONSOLE}
{$STRONGLINKTYPES ON}

uses
  System.SysUtils,
  WfEngine.GatewayService.Tests in 'tests\WfEngine.GatewayService.Tests.pas',
  WfEngine.Integration.Tests in 'tests\WfEngine.Integration.Tests.pas',
  WfEngine.Dialect in 'src\WfEngine.Dialect.pas',
  WfEngine.Types in 'src\WfEngine.Types.pas',
  WfEngine.Interfaces in 'src\WfEngine.Interfaces.pas',
  WfEngine.GatewayDb in 'src\WfEngine.GatewayDb.pas',
  WfEngine.WorkerApiAdapter in 'src\WfEngine.WorkerApiAdapter.pas',
  WfEngine.ServiceLoop in 'src\WfEngine.ServiceLoop.pas',
  WfEngine.GatewayDtos in 'src\WfEngine.GatewayDtos.pas',
  WfEngine.GatewayService in 'src\WfEngine.GatewayService.pas',
  WfEngine.GatewayHost in 'src\WfEngine.GatewayHost.pas';

begin
  try
    Writeln('WfEngine tests');
    Writeln('METHYLPIPELINE_DB = ', GetEnvironmentVariable('METHYLPIPELINE_DB'));
    Writeln;
    RunGatewayServiceTests;
    Writeln;
    RunAllIntegrationTests;
    Writeln;
    Writeln('All tests passed.');
  except
    on E: Exception do
    begin
      Writeln('FAILED: ', E.ClassName, ': ', E.Message);
      ExitCode := 1;
    end;
  end;
end.
