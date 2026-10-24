-- golden: ddl/add_field_foreign_key_to_field
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule, ddl/create_tag
-- params: [[], [], []]
-- verified: unverified
ALTER TABLE "TESTAPP_SCHEDULE" ADD COLUMN "TAG_ID" NVARCHAR(50);
ALTER TABLE "TESTAPP_SCHEDULE" ADD CONSTRAINT "TESTAPP_SCHEDULE_TAG_ID_EB229223_FK_TESTAPP_TAG_LABEL" FOREIGN KEY ("TAG_ID") REFERENCES "TESTAPP_TAG" ("LABEL");
CREATE INDEX "TESTAPP_SCHEDULE_TAG_ID_EB229223" ON "TESTAPP_SCHEDULE" ("TAG_ID");
