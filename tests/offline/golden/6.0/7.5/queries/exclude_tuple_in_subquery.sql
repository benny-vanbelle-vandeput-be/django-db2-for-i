-- golden: queries/exclude_tuple_in_subquery
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [[1]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE NOT (("TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER") IN (SELECT U0."COMPANY" AS "COMPANY", U0."NUMBER" AS "NUMBER" FROM "TESTAPP_ACCOUNT" U0 WHERE U0."NUMBER" > %s));
