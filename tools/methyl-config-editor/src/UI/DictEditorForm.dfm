object DictEditorForm: TDictEditorForm
  Left = 0
  Top = 0
  BorderStyle = bsDialog
  Caption = 'Dictionary Editor'
  ClientHeight = 360
  ClientWidth = 560
  Position = poScreenCenter
  OnDestroy = FormDestroy
  PixelsPerInch = 96
  TextHeight = 15
  object PanelBottom: TPanel
    Left = 0
    Top = 319
    Width = 560
    Height = 41
    Align = alBottom
    BevelOuter = bvNone
    TabOrder = 0
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
    ColWidths = (
      180
      360)
  end
end
