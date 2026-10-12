# Prepare an independent Pages publication

Start from [local setup](setup.md). The Broca data directory stays local; a new
publication directory holds a static snapshot and a minimal deployment workflow.
No framework or private setup files are copied into that directory.

From the Broca framework checkout, preview:

```sh
python -m broca --root /path/to/my-guides publication \
  --repos /path/to/Mind/repos.yaml --repo my-guides \
  --pages-url https://research.example/guides/ --brain /path/to/PyAutoBrain \
  --output /path/to/new-publication --branch main
```

The command validates saved owner evidence, renders the board and validates its
shared feed. It lists the destination and files without writing. Repeat with
`--apply` to create exactly:

- `site/index.html`
- `site/state.json`
- `.github/workflows/pages.yml`

The destination must be new, outside the data directory, with an existing parent.
Symlink destinations and existing directories are refused. The supported default
branch names contain letters, digits, hyphens or underscores; `main` is the default.
If writing is interrupted, inspect the partial bundle and generate into another
new directory. Existing publication checkouts are never overwritten by this command.

The feed and board work link use the canonical repository identity selected from
your Mind map. The Pages location is explicit; supplying it does not prove ownership
or configure a custom domain. Empty evidence remains unknown. Rendering does not
collect new evidence or advance its observation timestamps.

## Review, then deploy

Inspect both HTML and JSON before publishing. The file allowlist excludes local
setup files, paths and raw source records as files; it is not a privacy scanner.
Rendered content can include saved prompts, record descriptions, resource links
and other owner-supplied text. Review its visibility and intended audience.

Choose the destination repository matching the canonical identity. With explicit
publication approval, copy the reviewed bundle into that repository, commit it on
its chosen default branch and enable GitHub Pages using Actions. Resolve any
existing files or workflows manually. Custom-domain configuration and repository
creation are separate operator steps; this command performs no network or git
operations and changes no access settings.

The generated workflow checks that `site/` contains exactly two regular files,
checks the feed identity against the configured destination and current repository,
and uploads only `site/`. It runs validation on pull requests, and deploys only on
the selected branch for a push or manual dispatch. A dispatch on another branch
cannot deploy. The workflow reads only its own publication checkout: no Brain or
Broca installation, collection, evaluation or schedule is involved.

For updates, render another bundle from current saved evidence, review its diff,
and replace the two site files through the publication repository's normal review
process. Repeated rendering does not make old evidence fresh. Configuration or
branch changes also require reviewing the generated workflow diff.

## Connect and resume

After successful deployment, inspect the real HTTPS `state.json` under the configured
Pages directory. Use Scientist's existing `connect_organ.py` preview/apply with
`--organ broca`, your canonical map/key and that Pages directory. The independent
Scientist becomes connected only after its validator accepts the real feed.

For a fresh conversation, provide your canonical map, local Broca data directory,
publication repository and existing Mind task. Ask the assistant to inspect those
before rendering or proposing an update. The private setup handoff remains local;
do not upload it to help deployment. Missing or stale evidence after connection
remains evidence trouble for the connected organ.

Local bundle validation is not proof of a live deployment. No live independent
endpoint, pause control or full activation workflow is established by generating
this snapshot.
