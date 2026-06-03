object DictEditorForm: TDictEditorForm
  Left = 0
  Top = 0
  BorderStyle = bsDialog
  Caption = 'Dictionary Editor'
  ClientHeight = 360
  ClientWidth = 560
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Segoe UI'
  Font.Style = []
  Position = poScreenCenter
  OnDestroy = FormDestroy
  TextHeight = 15
  object PanelBottom: TPanel
    Left = 0
    Top = 319
    Width = 560
    Height = 41
    Align = alBottom
    BevelOuter = bvNone
    TabOrder = 0
    ExplicitTop = 287
    ExplicitWidth = 550
    object btnOK: TButton
      Left = 368
      Top = 8
      Width = 85
      Height = 25
      Caption = 'OK'
      Default = True
      TabOrder = 0
      OnClick = btnOKClick
    end
    object btnCancel: TButton
      Left = 459
      Top = 8
      Width = 85
      Height = 25
      Cancel = True
      Caption = 'Cancel'
      ModalResult = 2
      TabOrder = 1
    end
  end
  object PanelButtons: TPanel
    Left = 0
    Top = 0
    Width = 560
    Height = 41
    Align = alTop
    BevelOuter = bvNone
    TabOrder = 1
    ExplicitWidth = 550
    object btnAdd: TButton
      Left = 8
      Top = 8
      Width = 75
      Height = 25
      Caption = 'Add'
      TabOrder = 0
      OnClick = btnAddClick
    end
    object btnRemove: TButton
      Left = 89
      Top = 8
      Width = 75
      Height = 25
      Caption = 'Remove'
      TabOrder = 1
      OnClick = btnRemoveClick
    end
    object btnEdit: TButton
      Left = 170
      Top = 8
      Width = 75
      Height = 25
      Caption = 'Edit value...'
      TabOrder = 2
      OnClick = btnEditClick
    end
  end
  object StringGrid: TStringGrid
    Left = 0
    Top = 41
    Width = 560
    Height = 278
    Align = alClient
    ColCount = 2
    DefaultRowHeight = 22
    FixedCols = 0
    RowCount = 2
    Options = [goFixedVertLine, goFixedHorzLine, goVertLine, goHorzLine, goRangeSelect, goEditing]
    TabOrder = 2
    ExplicitWidth = 550
    ExplicitHeight = 246
    ColWidths = (
      180
      360)
  end
end
