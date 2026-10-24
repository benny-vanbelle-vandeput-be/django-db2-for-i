-- golden: ddl/alter_field_widen
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[], [], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-24
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "TEXT" SET DATA TYPE NVARCHAR(40);
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "NUMBER" SET DATA TYPE BIGINT;
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "AMOUNT" SET DATA TYPE DECIMAL(7, 3);
