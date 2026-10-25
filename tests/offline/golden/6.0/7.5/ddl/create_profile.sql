-- golden: ddl/create_profile
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-25
CREATE TABLE "TESTAPP_PROFILE" ("AUTHOR_ID" INTEGER NOT NULL PRIMARY KEY);
ALTER TABLE "TESTAPP_PROFILE" ADD CONSTRAINT "TESTAPP_PROFILE_AUTHOR_ID_CF6379B5_FK_TESTAPP_AUTHOR_ID" FOREIGN KEY ("AUTHOR_ID") REFERENCES "TESTAPP_AUTHOR" ("ID");
