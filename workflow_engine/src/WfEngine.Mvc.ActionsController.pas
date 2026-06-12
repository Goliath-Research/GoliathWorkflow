unit WfEngine.Mvc.ActionsController;

{
  DMVC controller for workflow action schema catalog routes.
}

interface

uses
  MVCFramework,
  MVCFramework.Commons,
  WfEngine.GatewayDtos,
  WfEngine.GatewayService;

type
  [MVCPath('/v1')]
  TActionsController = class(TMVCController)
  private
    FGateway: IGatewayService;
  public
    [MVCInject]
    constructor Create(const Gateway: IGatewayService); reintroduce;

    [MVCPath('/actions')]
    [MVCHTTPMethod([httpGET])]
    function ListActions: IMVCResponse;

    [MVCPath('/actions/($ActionName)/schema')]
    [MVCHTTPMethod([httpGET])]
    function GetActionSchema(const ActionName: string;
      [MVCFromQueryString('direction')] Direction: string = 'input'): IMVCResponse;
  end;

implementation

uses
  System.SysUtils;

{ TActionsController }

constructor TActionsController.Create(const Gateway: IGatewayService);
begin
  inherited Create;
  FGateway := Gateway;
end;

function TActionsController.ListActions: IMVCResponse;
begin
  Result := OKResponse(FGateway.ListActions);
end;

function TActionsController.GetActionSchema(const ActionName: string;
  Direction: string): IMVCResponse;
begin
  try
    Result := OKResponse(FGateway.GetActionSchema(ActionName, Direction));
  except
    on E: EActionSchemaNotFound do
      Result := NotFoundResponse(E.Message);
    on E: Exception do
      if SameText(E.Message, 'direction must be input or output') then
        Result := BadRequestResponse(E.Message)
      else
        raise;
  end;
end;

end.
