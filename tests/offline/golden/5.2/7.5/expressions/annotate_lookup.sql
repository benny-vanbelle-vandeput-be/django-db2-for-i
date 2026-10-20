-- golden: expressions/annotate_lookup
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[2, 2]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT CASE WHEN "TESTAPP_AUTHOR"."ID" < CAST(%s AS INTEGER) THEN TRUE WHEN NOT ("TESTAPP_AUTHOR"."ID" < CAST(%s AS INTEGER)) THEN FALSE END AS "X" FROM "TESTAPP_AUTHOR";
