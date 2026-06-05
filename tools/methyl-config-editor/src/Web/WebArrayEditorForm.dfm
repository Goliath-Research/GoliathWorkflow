object UniWebArrayEditorForm: TUniWebArrayEditorForm
  Left = 0
  Top = 0
  Width = 640
  Height = 480
  Text = ''
  BorderStyle = bsDialog
  Caption = 'Array Editor'
  Color = clBtnFace
  object PanelButtons: TUniPanel
    Left = 0
    Top = 0
    Width = 120
    Height = 430
    Hint = ''
    Align = alLeft
    TabOrder = 1
    Caption = ''
    object btnAdd: TUniButton
      Left = 10
      Top = 10
      Width = 100
      Height = 30
      Hint = ''
      Caption = 'Add'
      TabOrder = 1
      OnClick = btnAddClick
    end
    object btnRemove: TUniButton
      Left = 10
      Top = 45
      Width = 100
      Height = 30
      Hint = ''
      Caption = 'Remove'
      TabOrder = 2
      OnClick = btnRemoveClick
    end
    object btnEdit: TUniButton
      Left = 10
      Top = 80
      Width = 100
      Height = 30
      Hint = ''
      Caption = 'Edit'
      TabOrder = 3
      OnClick = btnEditClick
    end
    object btnUp: TUniButton
      Left = 10
      Top = 115
      Width = 100
      Height = 30
      Hint = ''
      Caption = 'Up'
      TabOrder = 4
      OnClick = btnUpClick
    end
    object btnDown: TUniButton
      Left = 10
      Top = 150
      Width = 100
      Height = 30
      Hint = ''
      Caption = 'Down'
      TabOrder = 5
      OnClick = btnDownClick
    end
  end
  object ListBox: TUniListBox
    Left = 120
    Top = 0
    Width = 520
    Height = 430
    Hint = ''
    Align = alClient
    TabOrder = 2
  end
  object PanelBottom: TUniPanel
    Left = 0
    Top = 430
    Width = 640
    Height = 50
    Hint = ''
    Align = alBottom
    TabOrder = 3
    Caption = ''
    object btnOK: TUniButton
      Left = 440
      Top = 10
      Width = 85
      Height = 30
      Hint = ''
      Caption = 'OK'
      TabOrder = 1
      OnClick = btnOKClick
    end
    object btnCancel: TUniButton
      Left = 535
      Top = 10
      Width = 85
      Height = 30
      Hint = ''
      Caption = 'Cancel'
      TabOrder = 2
      OnClick = btnCancelClick
    end
  end
end
