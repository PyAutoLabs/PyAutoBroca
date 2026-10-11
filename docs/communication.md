# Communication resource ownership

Broca covers documentation, tutorials (including HowTo), user-facing workspaces
and assistants. These are first-class resources even when no assistant exists.
Project repositories retain source, definitions, tutorials and maintenance work.
Scientist owns explicit project/resource relationships; Mind owns canonical repo
identities and implementation task state. Broca's resources.json is a generated
public projection, not a second registry or an evidence ledger.

Broca presents communication context and recorded upkeep/evaluation evidence.
Unknown evidence stays unknown. A docs build or passing tutorial does not prove
explanatory quality. Existing assistant records and receipts remain append-only.
The resource list does not create new evaluations or claim coverage for docs,
workspaces or tutorials whose evidence has not been collected.

Ears listens to community conversations; Memory holds durable knowledge; Cortex
holds scientific results; Heart owns technical validation and release readiness;
Hands executes builds/releases. Brain interprets and routes work. Broca links
these owners rather than duplicating their records or verdicts.

## Refresh the public inventory

From a workspace with compatible Scientist, Mind and Broca checkouts:

```sh
python3 PyAutoScientist/scripts/organism_board.py --catalogue \
  --projects PyAutoScientist/config/projects.json --repos PyAutoMind/repos.yaml \
  > public-resources.json
```

Validate that command succeeded, review the public projection, then copy it to
Broca's resources.json (and Heart's for the coordinated dashboard). Do not redirect
over the saved catalogue before validation succeeds. Commit the projection when
project relationships change. This export collects no evidence and copies no
project source. Only resources referenced by public projects and themselves
marked public enter the catalogue. Publication uses the saved inventory and
preserves original evidence dates; it does not refresh or evaluate anything.

Anchors are `resource-<Scientist resource ID>`. Shared resources appear once with
all public project contexts. Native details remain usable without JavaScript;
Brain's shared section navigation opens target details and their ancestors.
Canonical organism-description rollout remains tracked separately in Mind's
Broca communication contract; it must follow the available Brain/Mind claims.
