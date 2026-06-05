object UniMainForm: TUniMainForm
  Left = 0
  Top = 0
  Width = 960
  Height = 640
  Text = ''
  Caption = 'JSON Schema Editor (Web)'
  Color = clBtnFace
  object PanelTop: TUniPanel
    Left = 0
    Top = 0
    Width = 960
    Height = 90
    Hint = ''
    Align = alTop
    TabOrder = 1
    Caption = ''
    object lblSchema: TUniLabel
      Left = 16
      Top = 12
      Width = 45
      Height = 13
      Hint = ''
      Caption = 'Schema'
      TabOrder = 1
    end
    object cboSchema: TUniComboBox
      Left = 72
      Top = 8
      Width = 360
      Height = 23
      Hint = ''
      Text = ''
      TabOrder = 2
      OnChange = cboSchemaChange
    end
    object lblSchemasRoot: TUniLabel
      Left = 16
      Top = 44
      Width = 72
      Height = 13
      Hint = ''
      Caption = 'Schemas root'
      TabOrder = 3
    end
    object lblSchemasRootValue: TUniLabel
      Left = 104
      Top = 44
      Width = 500
      Height = 13
      Hint = ''
      Caption = '(server path)'
      TabOrder = 4
    end
    object btnNewJson: TUniButton
      Left = 456
      Top = 8
      Width = 90
      Height = 28
      Hint = ''
      Caption = 'New JSON'
      TabOrder = 5
      OnClick = btnNewJsonClick
    end
    object btnEditJson: TUniButton
      Left = 552
      Top = 8
      Width = 110
      Height = 28
      Hint = ''
      Caption = 'Edit properties'
      TabOrder = 6
      OnClick = btnEditJsonClick
    end
    object UploadJson: TUniFileUpload
      Left = 672
      Top = 8
      Width = 120
      Height = 28
      Hint = ''
      Filter = '.json'
      Messages.Uploading = 'Uploading...'
      Messages.PleaseWait = 'Please wait'
      Messages.UploadError = 'Upload error'
      Messages.UploadTimeout = 'Timeout occurred'
      Messages.Uploaded = 'Uploaded'
      Messages.UploadedMsg = 'Upload completed'
      Messages.BrowseText = 'Upload JSON'
      Messages.DragDropText = 'Drop JSON file'
      Overwrite = True
      OnCompleted = UploadJsonCompleted
    end
    object btnDownloadJson: TUniButton
      Left = 800
      Top = 8
      Width = 120
      Height = 28
      Hint = ''
      Caption = 'Download JSON'
      TabOrder = 7
      OnClick = btnDownloadJsonClick
    end
  end
  object MemoJson: TUniMemo
    Left = 0
    Top = 90
    Width = 960
    Height = 550
    Hint = ''
    Lines.Strings = (
      '{}')
    Align = alClient
    TabOrder = 2
    ReadOnly = True
  end
end
