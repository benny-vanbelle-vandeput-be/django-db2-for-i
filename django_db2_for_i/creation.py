"""DatabaseCreation: test database setup and teardown.

Supports a "use existing schema" mode that never runs CREATE/DROP SCHEMA
and cleans up its own tables (needed for PUB400). Implemented in phase 1.
"""
