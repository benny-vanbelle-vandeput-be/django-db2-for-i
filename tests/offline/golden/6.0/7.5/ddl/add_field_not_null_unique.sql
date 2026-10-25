-- golden: ddl/add_field_not_null_unique
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[], []]
-- verified: unverified
ALTER TABLE "TESTAPP_SCHEDULE" ADD COLUMN "SLUG" NVARCHAR(20) DEFAULT NOT NULL UNIQUE;
ALTER TABLE "TESTAPP_SCHEDULE" ALTER COLUMN "SLUG" DROP DEFAULT;
