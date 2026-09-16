EXEC portal.sp_upsert_credential
  @name = N'goliath-archive-keys',
  @version = N'1',
  @status = N'published',
  @provider = N's3',
  @secret_json = N'{"authMode":"explicit_keys","accessKeyId":"L35V18N1L0C72AR62K8I","secretAccessKey":"zRf5fACYOmU0PVpT4kDkFaIUW0Q6t80TUOW6XkaR"}';

EXEC portal.sp_publish_credential
  @name = N'goliath-archive-keys',
  @version = N'1';