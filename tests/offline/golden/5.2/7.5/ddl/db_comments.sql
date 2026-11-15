-- golden: ddl/db_comments
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[], [], [], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-15
COMMENT ON TABLE "TESTAPP_SCHEDULE" IS 'Planned work, it''s all';
COMMENT ON COLUMN "TESTAPP_SCHEDULE"."START" IS 'Start (UTC)';
COMMENT ON COLUMN "TESTAPP_SCHEDULE"."START" IS '';
COMMENT ON TABLE "TESTAPP_SCHEDULE" IS '';
