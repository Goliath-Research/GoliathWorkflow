/*
  Remove mistaken wf.platform_sample_storage (domain config belongs in portal schema).
  Deploy portal_resource_profile.sql first and migrate credentials if needed.
*/

IF OBJECT_ID('wf.platform_sample_storage', 'U') IS NOT NULL
BEGIN
    DROP TABLE wf.platform_sample_storage;
END
GO
