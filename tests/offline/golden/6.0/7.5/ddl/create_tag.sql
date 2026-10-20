-- golden: ddl/create_tag
-- django: 6.0
-- profile: 7.5
-- depends: -
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
CREATE TABLE "TESTAPP_TAG" ("ID" CHAR(32) NOT NULL PRIMARY KEY, "LABEL" NVARCHAR(50) NOT NULL UNIQUE);
