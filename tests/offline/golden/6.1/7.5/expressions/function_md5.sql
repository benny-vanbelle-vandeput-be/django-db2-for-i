-- golden: expressions/function_md5
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-11-03
SELECT LOWER(HEX(HASH_MD5(CAST("TESTAPP_AUTHOR"."NAME" AS CLOB(2G) CCSID 1208)))) AS "X" FROM "TESTAPP_AUTHOR";
