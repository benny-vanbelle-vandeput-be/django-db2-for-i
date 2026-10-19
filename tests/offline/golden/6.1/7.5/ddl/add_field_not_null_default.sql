-- golden: ddl/add_field_not_null_default
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
ALTER TABLE "TESTAPP_DEFAULTS" ADD COLUMN "NICKNAME" NVARCHAR(20) DEFAULT UX'004F00270042007200690065006E' NOT NULL;
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "NICKNAME" DROP DEFAULT;
