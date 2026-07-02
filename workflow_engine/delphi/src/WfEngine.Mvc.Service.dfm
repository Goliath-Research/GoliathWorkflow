object MethylWfGateway: TMethylWfGatewayService
  OldCreateOrder = False
  DisplayName = 'MethylPipeline Workflow Gateway'
  AllowPause = True
  AllowStop = True
  OnContinue = ServiceContinue
  OnPause = ServicePause
  OnStart = ServiceStart
  OnStop = ServiceStop
  Height = 150
  Width = 300
end
