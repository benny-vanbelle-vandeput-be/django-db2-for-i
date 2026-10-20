-- golden: queries/filter_tuple_exact_longer_than_column
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [["ab", 1]]
-- verified: unverified
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE ("TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER") = (CAST(%s AS NVARCHAR(32)), CAST(%s AS INTEGER));
