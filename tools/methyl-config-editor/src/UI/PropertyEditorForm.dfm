object PropertyEditorForm: TPropertyEditorForm
  Left = 0
  Top = 0
  BorderStyle = bsDialog
  Caption = 'Property Editor'
  ClientHeight = 480
  ClientWidth = 640
  Position = poScreenCenter
  OnCreate = FormCreate
  OnDestroy = FormDestroy
  PixelsPerInch = 96
  TextHeight = 15
  object PanelBottom: TPanel
    Left = 0
    Top = 439
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
      TabOrder = 1
      OnClick = btnCancelClickClick
    end
  end
  object ScrollBox: TScrollBox
    Left = 0
    Top = 0
    Width = 640
    Height = 439
    Align = alClient
    TabOrder = 1
  end
end
