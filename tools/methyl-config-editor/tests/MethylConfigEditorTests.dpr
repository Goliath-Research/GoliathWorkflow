program MethylConfigEditorTests;

{$IFNDEF CONSOLE_TESTRUNNER}
{$APPTYPE CONSOLE}
{$ENDIF}

uses
  System.SysUtils,
  DUnitX.Loggers.Console,
  DUnitX.TestFramework,
  SchemaLoaderTests in 'SchemaLoaderTests.pas',
  JsonPathTests in 'JsonPathTests.pas',
  JsonArrayOpsTests in 'JsonArrayOpsTests.pas',
  JsonSchemaLoader in '..\src\Schema\JsonSchemaLoader.pas',
  SchemaNode in '..\src\Schema\SchemaNode.pas',
  SchemaDocument in '..\src\Schema\SchemaDocument.pas',
  JsonPath in '..\src\Data\JsonPath.pas',
  JsonArrayOps in '..\src\Data\JsonArrayOps.pas';

var
  Runner: ITestRunner;
  Results: IRunResults;
  Logger: ITestLogger;

begin
  ReportMemoryLeaksOnShutdown := True;
  Runner := TDUnitX.CreateRunner;
  Runner.UseRTTI := True;
  Logger := TDUnitXConsoleLogger.Create(True);
  Runner.AddLogger(Logger);
  Results := Runner.Execute;
  if not Results.AllPassed then
    ExitCode := 1
  else
    ExitCode := 0;
end.
