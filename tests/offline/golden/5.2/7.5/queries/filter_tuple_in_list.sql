-- golden: queries/filter_tuple_in_list
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [["a", 1, "b", 2]]
-- verified: unverified
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE (("TESTAPP_CONTACT"."COMPANY" = %s AND "TESTAPP_CONTACT"."ACCOUNT_NUMBER" = %s) OR ("TESTAPP_CONTACT"."COMPANY" = %s AND "TESTAPP_CONTACT"."ACCOUNT_NUMBER" = %s));
