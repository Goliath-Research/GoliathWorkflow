object MainForm: TMainForm
  Left = 0
  Top = 0
  Caption = 'MethylPipeline Config Editor'
  ClientHeight = 441
  ClientWidth = 720
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Segoe UI'
  Font.Style = []
  Position = poScreenCenter
  OnCreate = FormCreate
  OnDestroy = FormDestroy
  TextHeight = 15
  object PanelTop: TPanel
    Left = 0
    Top = 0
    Width = 720
    Height = 105
    Align = alTop
    BevelOuter = bvNone
    TabOrder = 0
    DesignSize = (
      720
      105)
    object lblSchema: TLabel
      Left = 8
      Top = 12
      Width = 42
      Height = 15
      Caption = 'Schema'
    end
    object lblSchemasRoot: TLabel
      Left = 8
      Top = 68
      Width = 72
      Height = 15
      Caption = 'Schemas root'
    end
    object cboSchema: TComboBox
      Left = 8
      Top = 33
      Width = 697
      Height = 23
      Style = csDropDownList
      Anchors = [akLeft, akTop, akRight]
      TabOrder = 0
      OnChange = cboSchemaChange
    end
    object edtSchemasRoot: TEdit
      Left = 88
      Top = 65
      Width = 545
      Height = 23
      Anchors = [akLeft, akTop, akRight]
      TabOrder = 1
    end
    object btnBrowseSchemas: TButton
      Left = 639
      Top = 63
      Width = 66
      Height = 25
      Anchors = [akTop, akRight]
      Caption = 'Browse...'
      TabOrder = 2
      OnClick = btnBrowseSchemasClick
    end
  end
  object MemoJson: TMemo
    Left = 0
    Top = 105
    Width = 720
    Height = 336
    Align = alClient
    Font.Charset = DEFAULT_CHARSET
    Font.Color = clWindowText
    Font.Height = -13
    Font.Name = 'Consolas'
    Font.Style = []
    ParentFont = False
    ReadOnly = True
    ScrollBars = ssBoth
    TabOrder = 1
    WordWrap = False
  end
  object MainMenu: TMainMenu
    Left = 640
    Top = 120
    object mnuFile: TMenuItem
      Caption = '&File'
      object mnuOpenJson: TMenuItem
        Caption = '&Open JSON...'
        ShortCut = 16463
        OnClick = mnuOpenJsonClick
      end
      object mnuSaveJson: TMenuItem
        Caption = '&Save JSON...'
        ShortCut = 16467
        OnClick = mnuSaveJsonClick
      end
      object mnuSep1: TMenuItem
        Caption = '-'
      end
      object mnuExit: TMenuItem
        Caption = 'E&xit'
        OnClick = mnuExitClick
      end
    end
    object mnuEdit: TMenuItem
      Caption = '&Edit'
      object mnuEditProperties: TMenuItem
        Caption = '&Edit properties...'
        ShortCut = 16453
        OnClick = mnuEditPropertiesClick
      end
      object mnuReloadCatalog: TMenuItem
        Caption = '&Reload schema catalog'
        OnClick = mnuReloadCatalogClick
      end
    end
  end
  object OpenDialogJson: TOpenDialog
    Filter = 'JSON files (*.json)|*.json|All files (*.*)|*.*'
    Left = 568
    Top = 120
  end
  object SaveDialogJson: TSaveDialog
    Filter = 'JSON files (*.json)|*.json|All files (*.*)|*.*'
    Left = 496
    Top = 120
  end
  object FileOpenDialog: TFileOpenDialog
    FavoriteLinks = <>
    FileTypes = <>
    Options = []
    Left = 424
    Top = 120
  end
end
