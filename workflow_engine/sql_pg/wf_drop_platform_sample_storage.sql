/*
  Remove mistaken wf.platform_sample_storage (domain config belongs in portal schema).
  Deploy portal_resource_profile.sql first and migrate credentials if needed.
*/

DROP TABLE IF EXISTS wf.platform_sample_storage;
