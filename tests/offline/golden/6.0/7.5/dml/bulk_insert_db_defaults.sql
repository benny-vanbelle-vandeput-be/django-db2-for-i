-- golden: dml/bulk_insert_db_defaults
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[5, "set", false]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-31
SELECT "ID", "TEXT", "FLAG", "NUMBER", "AMOUNT", "RATIO", "DAY", "CLOCK", "STAMP", "DATA", "CODE", "NOTHING" FROM FINAL TABLE (INSERT INTO "TESTAPP_DEFAULTS" ("TEXT", "FLAG", "NUMBER") VALUES (DEFAULT, DEFAULT, %s), (%s, %s, DEFAULT)) ORDER BY INPUT SEQUENCE;
