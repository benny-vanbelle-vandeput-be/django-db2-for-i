-- golden: ddl/rename_table
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_switch
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-24
RENAME TABLE "TESTAPP_SWITCH" TO "TESTAPP_LIGHTSWITCH";
RENAME TABLE "TESTAPP_LIGHTSWITCH" TO "TESTAPP_SWITCH";
