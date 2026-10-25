-- golden: ddl/add_field_not_null_no_default
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[], []]
-- verified: unverified
ALTER TABLE "TESTAPP_SCHEDULE" ADD COLUMN "POSITION" BIGINT DEFAULT NOT NULL;
ALTER TABLE "TESTAPP_SCHEDULE" ALTER COLUMN "POSITION" DROP DEFAULT;
