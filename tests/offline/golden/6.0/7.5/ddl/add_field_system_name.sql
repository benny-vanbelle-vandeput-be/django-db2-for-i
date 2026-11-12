-- golden: ddl/add_field_system_name
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[]]
-- verified: unverified
ALTER TABLE "TESTAPP_SCHEDULE" ADD COLUMN "PLANNED_MINUTES" FOR COLUMN PLANMIN INTEGER;
