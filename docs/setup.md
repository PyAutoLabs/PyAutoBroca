# Set up your own local Broca data

Use an existing Broca framework checkout with its Python dependencies and a
compatible Brain checkout. Keep user data in a separate directory. Register your
chosen repository identity in your canonical Mind `repos.yaml` first; its key and
GitHub name need not contain “Broca”. No GitHub access is needed for local setup.

From the Broca framework checkout:

```sh
python -m broca --root /path/to/my-guides setup \
  --repos /path/to/Mind/repos.yaml --repo my-guides \
  --pages-url https://research.example/guides/ --brain /path/to/PyAutoBrain
```

Review the file list, then repeat with `--apply`. The parent directory must exist.
A new destination or an empty directory is accepted; an existing nonempty directory
requires the matching setup manifest. Symlink destinations are refused.

Setup creates four files: `setup.json`, `assistants.json`, `CHECKIN.md` and
`SETUP.md`. The manifest stores the identity and local paths needed to resume.
Assistant selection starts empty. There are no copied measurements, collection
receipts, task records or invented resource inventories. Setup does not install
Python dependencies, clone repositories or configure a harness.

Each file is created atomically without replacing an existing file. After an
interruption, rerun the same command: matching files remain untouched and missing
files are filled in. A conflicting setup file stops the operation before writes;
inspect it manually. A crash before the first manifest was published may leave a
`.broca-setup-*` temporary file; inspect that new destination before removing only
that temporary file and retrying. Do not run setup concurrently with manual edits.

Once you customize configuration, validate it with `check` and `render`; setup
will refuse to restore defaults over your changes. It is an initializer, not an
upgrade or repair command. Keep the same framework version and paths when resuming
an unfinished setup. Record-preserving upgrades remain a separate pilot phase.

## Validate and resume

The generated `SETUP.md` has commands with your actual paths for:

- Previewing and resuming setup from a fresh conversation.
- Checking saved owner records with `python -m broca --root … check`.
- Rendering a local `site/index.html` and `site/state.json` with canonical identity.

Applying setup validates the local owner state and shared feed contract. Rendering
remains an explicit command. With no collection evidence, the feed is grey and its
required timestamp is the unknown-time sentinel, not the setup time. Resource
inventory remains unavailable until generated through the existing communication
inventory procedure. Setup success is not evidence of communication quality.

Keep `SETUP.md` and `setup.json` private: they contain local paths. They record
setup inputs and resumption instructions; the existing Mind task owns task status.
Project source and research records stay in their existing homes.

## Connect it to Scientist

Use the [publication bundle guide](publication.md) to prepare reviewed HTML, feed
and a minimal Pages workflow for an independent destination. Publish through a
separately approved publication task. Local setup neither checks remote ownership nor creates a
repository, publishes content, schedules upkeep or evaluates assistants.

When the real HTTPS feed is available, use Scientist's existing
`connect_organ.py` preview/apply with organ key `broca`, your canonical repository
key and the configured Pages directory. Until that check succeeds, this is local
setup, not an active Scientist connection. Subsequent stale or unavailable evidence
must remain visible as evidence trouble for the connected organ.
