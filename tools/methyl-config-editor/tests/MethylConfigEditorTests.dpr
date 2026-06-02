program MethylConfigEditorTests;

{$IFNDEF CONSOLE_TESTRUNNER}
{$APPTYPE CONSOLE}
{$ENDIF}

uses
  System.SysUtils,
  DUnitX.Loggers.Console,
  DUnitX.Loggers.Xml.NUnit,
  DUnitX.TestFramework,
  SchemaLoaderTests in 'SchemaLoaderTests.pas',
  JsonPathTests in 'JsonPathTests.pas';

var
  Runner: ITestRunner;
  Results: IRunResults;
  Logger: ITestLogger;
  NUnitLogger: ITestLogger;

begin
  ReportMemoryLeaksOnShutdown := True;
  Runner := TDUnitX.CreateRunner;
  Runner.UseRTTI := True;
  Runner.FixtureProvider := TDUnitXFixtureProvider.Create;
  Logger := TDUnitXConsoleLogger.Create(True);
  Runner.AddLogger(Logger);
  NUnitLogger := TDUnitXNUnitFileLogger.Create(TDUnitX.Options.XMLOutputFile);
  Runner.AddLogger(NUnitLogger);
  Results := Runner.Execute;
  if not Results.AllPassed then
    ExitCode := 1
  else
    ExitCode := 0;
end.
