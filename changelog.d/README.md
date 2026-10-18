# Changelog fragments

Every pull request with a user-visible change adds one file here instead of
editing `CHANGELOG.md`, so parallel pull requests do not conflict:

    changelog.d/<name>.<type>.md

- `<name>`: the pull request number (the entry gets a `(#<number>)`
  reference), or a short kebab-case topic when the number is not known yet.
- `<type>`, in the order of the CHANGELOG headings:
  `added` (Added), `enabled` (Enabled features: a feature flag switched on),
  `changed` (Changed), `fixed` (Fixed), `limitation` (Known limitations).
- Content: one entry in Markdown (wrapped at about 75 characters, no leading
  `- `), or several entries as a list of `- ` items.

`python scripts/assemble_changelog.py check` validates the files (the offline
tier runs it too), `draft` prints the section they would make, and
`release <version>` writes them into `CHANGELOG.md` and deletes them (see
CONTRIBUTING.md, "Releases").
