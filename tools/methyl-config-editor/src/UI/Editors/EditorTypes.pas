unit EditorTypes;

interface

uses
  Vcl.Controls,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  System.JSON,
  System.Classes,
  Spring.Collections,
  SchemaNode;

type
  TNotifyEventProc = reference to procedure(Sender: TObject);
  TKeyEventProc = reference to procedure(Sender: TObject; var Key: Word;
    Shift: TShiftState);
  TNotifyEventHandler = class
  private
    FProc: TNotifyEventProc;
  public
    constructor Create(const AProc: TNotifyEventProc);
    procedure Notify(Sender: TObject);
  end;

  TKeyEventHandler = class
  private
    FProc: TKeyEventProc;
  public
    constructor Create(const AProc: TKeyEventProc);
    procedure KeyDown(Sender: TObject; var Key: Word; Shift: TShiftState);
  end;

  TPropertyRow = class;

  IPropertyEditorContext = interface
    ['{A1B2C3D4-1234-5678-90AB-CDEF12345678}']
    function GetOwner: TComponent;
    function GetObjectSchema: TSchemaNode;
    function GetBreadcrumb: string;
    function GetPropertyValue(const AName: string): TJSONValue;
    procedure SetPropertyValue(const AName: string; AValue: TJSONValue);
    procedure ClearPropertyValue(const AName: string);
    procedure RebuildRows;
    function ChildBreadcrumb(const ASegment: string): string;
  end;

  ISchemaPropertyEditor = interface
    ['{E8A4B2C1-5D3F-4A2B-9C1E-7F6D5E4C3B2A}']
    function CanEdit(ANode: TSchemaNode): Boolean;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue);
    procedure ReadRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow);
    procedure UpdateSummary(ARow: TPropertyRow; AValue: TJSONValue);
    function EditValue(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue): TJSONValue;
  end;

  TPropertyRow = class
  private
    FEventHandlers: IList<TNotifyEventHandler>;
    FKeyHandlers: IList<TKeyEventHandler>;
  public
    GridRow: Integer;
    DisplayName: string;
    PropertyName: string;
    SchemaNode: TSchemaNode;
    Editor: ISchemaPropertyEditor;
    lblName: TLabel;
    ValuePanel: TPanel;
    ValueControl: TWinControl;
    btnEdit: TButton;
    btnClear: TButton;
    chkNull: TCheckBox;
    ErrorLabel: TLabel;
    constructor Create;
    destructor Destroy; override;
    function BindNotify(const AProc: TNotifyEventProc): TNotifyEvent;
    function BindKeyDown(const AProc: TKeyEventProc): TKeyEvent;
  end;

implementation

constructor TNotifyEventHandler.Create(const AProc: TNotifyEventProc);
begin
  inherited Create;
  FProc := AProc;
end;

procedure TNotifyEventHandler.Notify(Sender: TObject);
begin
  if Assigned(FProc) then
    FProc(Sender);
end;

constructor TKeyEventHandler.Create(const AProc: TKeyEventProc);
begin
  inherited Create;
  FProc := AProc;
end;

procedure TKeyEventHandler.KeyDown(Sender: TObject; var Key: Word;
  Shift: TShiftState);
begin
  if Assigned(FProc) then
    FProc(Sender, Key, Shift);
end;

constructor TPropertyRow.Create;
begin
  inherited Create;
  FEventHandlers := TCollections.CreateObjectList<TNotifyEventHandler>(True);
  FKeyHandlers := TCollections.CreateObjectList<TKeyEventHandler>(True);
end;

destructor TPropertyRow.Destroy;
begin
  FEventHandlers := nil;
  FKeyHandlers := nil;
  inherited;
end;

function TPropertyRow.BindNotify(const AProc: TNotifyEventProc): TNotifyEvent;
var
  Handler: TNotifyEventHandler;
begin
  Handler := TNotifyEventHandler.Create(AProc);
  FEventHandlers.Add(Handler);
  Result := Handler.Notify;
end;

function TPropertyRow.BindKeyDown(const AProc: TKeyEventProc): TKeyEvent;
var
  Handler: TKeyEventHandler;
begin
  Handler := TKeyEventHandler.Create(AProc);
  FKeyHandlers.Add(Handler);
  Result := Handler.KeyDown;
end;

end.
