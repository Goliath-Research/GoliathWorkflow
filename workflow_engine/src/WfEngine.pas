unit WfEngine;

{
  Umbrella unit for the Delphi workflow REST gateway library.
  HTTP hosting (DMVC controller / web module / Windows service) lives in
  the WfEngineSrv project; this package covers the SQL gateway core.
}

interface

uses
  WfEngine.Dialect,
  WfEngine.GatewayDb,
  WfEngine.Interfaces,
  WfEngine.RestApi,
  WfEngine.ServiceLoop,
  WfEngine.Types,
  WfEngine.WorkerApiAdapter;

implementation

end.
