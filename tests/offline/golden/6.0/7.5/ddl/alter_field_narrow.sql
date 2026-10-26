-- golden: ddl/alter_field_narrow
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-26
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "TEXT" SET DATA TYPE NVARCHAR(20);
