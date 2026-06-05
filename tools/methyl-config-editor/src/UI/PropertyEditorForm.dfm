object PropertyEditorForm: TPropertyEditorForm
  Left = 0
  Top = 0
  BorderStyle = bsDialog
  Caption = 'Property Editor'
  ClientHeight = 742
  ClientWidth = 640
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Segoe UI'
  Font.Style = []
  Position = poDefault
  OnCreate = FormCreate
  OnDestroy = FormDestroy
  TextHeight = 15
  object PanelBottom: TPanel
    Left = 0
    Top = 701
    Width = 640
    Height = 41
    Align = alBottom
    BevelOuter = bvNone
    TabOrder = 0
    object btnOK: TButton
      Left = 448
      Top = 8
      Width = 85
      Height = 25
      Caption = 'OK'
      Default = True
      TabOrder = 0
      OnClick = btnOKClick
    end
    object btnCancel: TButton
      Left = 539
      Top = 8
      Width = 85
      Height = 25
      Cancel = True
      Caption = 'Cancel'
      ModalResult = 2
      TabOrder = 1
      OnClick = btnCancelClick
    end
  end
  object ScrollBox: TScrollBox
    Left = 0
    Top = 0
    Width = 640
    Height = 701
    Align = alClient
    TabOrder = 1
  end
end
