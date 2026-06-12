program WfEngineTests;

{$APPTYPE CONSOLE}
{$STRONGLINKTYPES ON}

uses
  System.SysUtils,
  WfEngine.GatewayService.Tests in 'tests\WfEngine.GatewayService.Tests.pas',
  WfEngine.Integration.Tests in 'tests\WfEngine.Integration.Tests.pas';

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
