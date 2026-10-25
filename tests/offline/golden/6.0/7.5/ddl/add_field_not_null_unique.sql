-- golden: ddl/add_field_not_null_unique
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-25
ALTER TABLE "TESTAPP_SCHEDULE" ADD COLUMN "SLUG" NVARCHAR(20) DEFAULT NOT NULL UNIQUE;
ALTER TABLE "TESTAPP_SCHEDULE" ALTER COLUMN "SLUG" DROP DEFAULT;
