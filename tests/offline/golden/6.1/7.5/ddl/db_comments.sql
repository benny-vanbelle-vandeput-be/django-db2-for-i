-- golden: ddl/db_comments
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[], [], [], []]
-- verified: unverified
COMMENT ON TABLE "TESTAPP_SCHEDULE" IS 'Planned work, it''s all';
COMMENT ON COLUMN "TESTAPP_SCHEDULE"."START" IS 'Start (UTC)';
COMMENT ON COLUMN "TESTAPP_SCHEDULE"."START" IS '';
COMMENT ON TABLE "TESTAPP_SCHEDULE" IS '';
