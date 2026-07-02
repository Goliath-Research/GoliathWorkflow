unit WfEngine.GatewayDtos;

{
  OpenAPI-aligned request/response DTOs for the workflow REST gateway.
  Field names match contracts/openapi.yaml (snake_case) for DMVC JSON binding.
}

interface

uses
  System.JSON,
  System.SysUtils;

type
  TWorkerAuthRequest = class
  public
    worker_id: Int64;
    worker_token: string;
  end;

  TWorkerRequestTaskRequest = class
  public
    worker_id: Int64;
    worker_token: string;
    capability: string;
    max_lease_seconds: Integer;
    constructor Create;
  end;

  TWorkerSubmitResultRequest = class
  public
    worker_id: Int64;
    worker_token: string;
    result_code: Integer;
    output_json: TJSONValue;
    constructor Create;
    destructor Destroy; override;
  end;

  TWorkerHeartbeatRequest = class
  public
    worker_id: Int64;
    worker_token: string;
    extend_seconds: Integer;
    constructor Create;
  end;

  TWorkerFailTaskRequest = class
  public
    worker_id: Int64;
    worker_token: string;
    error_code: Integer;
    error_message: string;
  end;

  TWorkerTaskClaimResponse = class
  public
    has_task: Boolean;
    node_execution_id: Int64;
    workflow_instance_id: Int64;
    node_key: string;
    action_name: string;
    capability: string;
    attempt_no: Integer;
    input_json: TJSONValue;
    iteration_no: Integer;
    constructor Create;
    destructor Destroy; override;
  end;

  TWorkerSubmitResultResponse = class
  public
    accepted: Boolean;
    instance_status: string;
    next_ready_count: Integer;
  end;

  TWorkerHeartbeatResponse = class
  public
    rows_updated: Integer;
  end;

  TCreateInstanceRequest = class
  public
    workflow_version_id: Int64;
    context_json: TJSONValue;
    constructor Create;
    destructor Destroy; override;
  end;

  TWorkflowInstanceSummary = class
  public
    id: Int64;
    workflow_version_id: Int64;
    status: string;
  end;

  TDeleteDefinitionResponse = class
  public
    deleted_instance_count: Integer;
    deleted_version_count: Integer;
  end;

  TActionSummary = class
  public
    action_name: string;
    capability: string;
    has_input_schema: Boolean;
    has_output_schema: Boolean;
  end;

  TActionListResponse = class
  public
    actions: TArray<TActionSummary>;
    constructor Create;
    destructor Destroy; override;
  end;

  TActionSchemaResponse = class
  public
    action_name: string;
    direction: string;
    schema_id: string;
    schema_json: TJSONValue;
    constructor Create;
    destructor Destroy; override;
  end;

implementation

constructor TWorkerRequestTaskRequest.Create;
begin
  inherited Create;
  max_lease_seconds := 300;
end;

constructor TWorkerSubmitResultRequest.Create;
begin
  inherited Create;
  output_json := nil;
end;

destructor TWorkerSubmitResultRequest.Destroy;
begin
  output_json.Free;
  inherited;
end;

constructor TWorkerHeartbeatRequest.Create;
begin
  inherited Create;
  extend_seconds := 300;
end;

constructor TWorkerTaskClaimResponse.Create;
begin
  inherited Create;
  input_json := nil;
end;

destructor TWorkerTaskClaimResponse.Destroy;
begin
  input_json.Free;
  inherited;
end;

constructor TCreateInstanceRequest.Create;
begin
  inherited Create;
  context_json := nil;
end;

destructor TCreateInstanceRequest.Destroy;
begin
  context_json.Free;
  inherited;
end;

constructor TActionListResponse.Create;
begin
  inherited Create;
  SetLength(actions, 0);
end;

destructor TActionListResponse.Destroy;
var
  I: Integer;
begin
  for I := 0 to High(actions) do
    actions[I].Free;
  inherited;
end;

constructor TActionSchemaResponse.Create;
begin
  inherited Create;
  schema_json := nil;
end;

destructor TActionSchemaResponse.Destroy;
begin
  schema_json.Free;
  inherited;
end;

end.
