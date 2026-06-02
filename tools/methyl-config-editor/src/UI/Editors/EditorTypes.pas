unit EditorTypes;

interface

uses
  Vcl.Controls,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  System.JSON,
  System.Classes,
  SchemaNode;

type
  IPropertyEditorContext = interface;
  TPropertyRow = class;

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
  public
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
  end;

implementation

end.
