-- golden: ddl/alter_field_null
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-24
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "NUMBER" DROP NOT NULL;
