-- golden: ddl/add_field_system_name
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.10, 2026-11-13
ALTER TABLE "TESTAPP_SCHEDULE" ADD COLUMN "PLANNED_MINUTES" FOR COLUMN PLANMIN INTEGER;
