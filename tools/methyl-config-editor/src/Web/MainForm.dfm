object UniMainForm: TUniMainForm
  Left = 0
  Top = 0
  ClientHeight = 601
  ClientWidth = 944
  Caption = 'JSON Schema Editor (Web)'
  OldCreateOrder = False
  MonitoredKeys.Keys = <>
  TextHeight = 15
  object PanelTop: TUniPanel
    Left = 0
    Top = 0
    Width = 944
    Height = 90
    Hint = ''
    Align = alTop
    TabOrder = 1
    Caption = ''
    object lblSchema: TUniLabel
      Left = 16
      Top = 12
      Width = 39
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
      IconItems = <>
      OnChange = cboSchemaChange
    end
    object lblSchemasRoot: TUniLabel
      Left = 16
      Top = 44
      Width = 69
      Height = 13
      Hint = ''
      Caption = 'Schemas root'
      TabOrder = 3
    end
    object lblSchemasRootValue: TUniLabel
      Left = 104
      Top = 44
      Width = 63
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
    Width = 944
    Height = 511
    Hint = ''
    Lines.Strings = (
      '{}')
    Align = alClient
    ReadOnly = True
    TabOrder = 0
  end
  object UploadJson: TUniFileUpload
    Filter = '.json'
    Title = 'Upload'
    Messages.Uploading = 'Uploading...'
    Messages.PleaseWait = 'Please wait'
    Messages.Cancel = 'Cancel'
    Messages.Processing = 'Processing...'
    Messages.UploadError = 'Upload error'
    Messages.Upload = 'Upload'
    Messages.NoFileError = 'Please select a file'
    Messages.BrowseText = 'Upload JSON'
    Messages.UploadTimeout = 'Timeout occurred'
    Messages.MaxSizeError = 'File is bigger than maximum allowed size'
    Messages.MaxFilesError = 'You can upload maximum %d files.'
    Overwrite = True
    Width = 120
    OnCompleted = UploadJsonCompleted
    Left = 672
    Top = 8
  end
end
