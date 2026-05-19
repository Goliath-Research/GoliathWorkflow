program WfEngineTests;

{$APPTYPE CONSOLE}
{$STRONGLINKTYPES ON}

uses
  System.SysUtils,
  WfEngine.Integration.Tests in 'tests\WfEngine.Integration.Tests.pas';

begin
  try
    Writeln('WfEngine integration tests');
    Writeln('METHYLPIPELINE_DB = ', GetEnvironmentVariable('METHYLPIPELINE_DB'));
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
