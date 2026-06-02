unit WfEngine.Logger;

interface

uses
  System.SysUtils, System.IOUtils, System.DateUtils, WfEngine.Interfaces;

type
  TWfEngineLogger = class(TInterfacedObject, IWfEngineLogger)
  private
    FLogPath: string;
    procedure Log(const ALevel, AMessage: string);
  public
    constructor Create(const ALogPath: string = '');
    procedure Info(const AMessage: string);
    procedure Warn(const AMessage: string);
    procedure Error(const AMessage: string);
  end;

implementation

uses
  System.Classes;

constructor TWfEngineLogger.Create(const ALogPath: string);
begin
  if ALogPath <> '' then
    FLogPath := ALogPath
  else
    FLogPath := GetEnvironmentVariable('METHYLPIPELINE_LOG');
  if FLogPath = '' then
  begin
    // default to working directory log file
    FLogPath := TPath.Combine(GetCurrentDir, 'wfengine.log');
  end;
end;

procedure TWfEngineLogger.Log(const ALevel, AMessage: string);
var
  Line: string;
begin
  Line := Format('%s [%s] %s', [FormatDateTime('yyyy-mm-dd hh:nn:ss.zzz', Now), ALevel, AMessage]);
  // Console
  try
    Writeln(Line);
  except
    // ignore
  end;
  // File (append) - swallow errors to avoid crashing the service on logging failure
  try
    TFile.AppendAllText(FLogPath, Line + sLineBreak, TEncoding.UTF8);
  except
    // ignore logging errors
  end;
end;

procedure TWfEngineLogger.Info(const AMessage: string);
begin
  Log('INFO', AMessage);
end;

procedure TWfEngineLogger.Warn(const AMessage: string);
begin
  Log('WARN', AMessage);
end;

procedure TWfEngineLogger.Error(const AMessage: string);
begin
  Log('ERROR', AMessage);
end;

end.