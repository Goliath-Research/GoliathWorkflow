object ArrayEditorForm: TArrayEditorForm
  Left = 0
  Top = 0
  BorderStyle = bsDialog
  Caption = 'Array Editor'
  ClientHeight = 360
  ClientWidth = 520
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
    Width = 520
    Height = 41
    Align = alBottom
    BevelOuter = bvNone
    TabOrder = 0
    object btnOK: TButton
      Left = 328
      Top = 8
      Width = 85
      Height = 25
      Caption = 'OK'
      Default = True
      TabOrder = 0
      OnClick = btnOKClick
    end
    object btnCancel: TButton
      Left = 419
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
    Width = 520
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
      Caption = 'Edit...'
      TabOrder = 2
      OnClick = btnEditClick
    end
    object btnUp: TButton
      Left = 251
      Top = 8
      Width = 55
      Height = 25
      Caption = 'Up'
      TabOrder = 3
      OnClick = btnUpClick
    end
    object btnDown: TButton
      Left = 312
      Top = 8
      Width = 55
      Height = 25
      Caption = 'Down'
      TabOrder = 4
      OnClick = btnDownClick
    end
  end
  object ListBox: TListBox
    Left = 0
    Top = 41
    Width = 520
    Height = 278
    Align = alClient
    ItemHeight = 15
    TabOrder = 2
  end
end
