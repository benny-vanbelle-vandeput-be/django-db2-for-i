-- golden: ddl/create_tag
-- django: 5.2
-- profile: 7.5
-- depends: -
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-14
CREATE TABLE "TESTAPP_TAG" ("ID" CHAR(32) NOT NULL PRIMARY KEY, "LABEL" NVARCHAR(50) NOT NULL UNIQUE);
