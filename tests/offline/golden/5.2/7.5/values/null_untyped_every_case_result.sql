-- golden: values/null_untyped_every_case_result
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-07
SELECT CASE WHEN "TESTAPP_AUTHOR"."NAME" = %s THEN CAST(NULL AS NVARCHAR(32)) ELSE CAST(NULL AS NVARCHAR(32)) END AS "X" FROM "TESTAPP_AUTHOR";
