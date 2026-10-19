-- golden: expressions/annotate_lookup
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[2]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT CASE WHEN "TESTAPP_AUTHOR"."ID" < CAST(%s AS INTEGER) THEN TRUE ELSE FALSE END AS "X" FROM "TESTAPP_AUTHOR";
