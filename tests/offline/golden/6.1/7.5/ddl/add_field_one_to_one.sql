-- golden: ddl/add_field_one_to_one
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_switch, ddl/create_author
-- params: [[], []]
-- verified: unverified
ALTER TABLE "TESTAPP_SWITCH" ADD COLUMN "AUTHOR_ID" INTEGER UNIQUE;
ALTER TABLE "TESTAPP_SWITCH" ADD CONSTRAINT "TESTAPP_SWITCH_AUTHOR_ID_F2661DC9_FK_TESTAPP_AUTHOR_ID" FOREIGN KEY ("AUTHOR_ID") REFERENCES "TESTAPP_AUTHOR" ("ID");
