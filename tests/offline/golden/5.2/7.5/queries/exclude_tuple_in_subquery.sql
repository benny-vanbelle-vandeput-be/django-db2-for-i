-- golden: queries/exclude_tuple_in_subquery
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [[1]]
-- verified: unverified
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE NOT (("TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER") IN (SELECT U0."COMPANY" AS "COMPANY", U0."NUMBER" AS "NUMBER" FROM "TESTAPP_ACCOUNT" U0 WHERE U0."NUMBER" > %s));
