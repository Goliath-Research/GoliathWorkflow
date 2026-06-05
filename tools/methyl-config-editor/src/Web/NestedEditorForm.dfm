object UniNestedEditorForm: TUniNestedEditorForm
  Left = 0
  Top = 0
  Width = 720
  Height = 520
  Text = ''
  BorderStyle = bsDialog
  Caption = 'Property Editor'
  Color = clBtnFace
  object PropertyGrid: TUniPropertyGrid
    Left = 0
    Top = 0
    Width = 720
    Height = 470
    Hint = ''
    Align = alClient
    TabOrder = 1
    LayoutConfig.BodyPadding = 5
  end
  object PanelBottom: TUniPanel
    Left = 0
    Top = 470
    Width = 720
    Height = 50
    Hint = ''
    Align = alBottom
    TabOrder = 2
    Caption = ''
    object btnOK: TUniButton
      Left = 520
      Top = 10
      Width = 85
      Height = 30
      Hint = ''
      Caption = 'OK'
      TabOrder = 1
      OnClick = btnOKClick
    end
    object btnCancel: TUniButton
      Left = 615
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
