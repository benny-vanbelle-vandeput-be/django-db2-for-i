-- golden: ddl/alter_field_narrow
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: unverified
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "TEXT" SET DATA TYPE NVARCHAR(20);
