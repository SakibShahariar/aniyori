# Contributing to Aniyori

Thanks for helping build Aniyori.

## Current milestone

The project is in its initial application-shell phase. Keep changes small and test them locally before opening a pull request.

## Development setup

On Debian or Ubuntu, install the GTK runtime and Python bindings:

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

Run the app from the repository root:

```bash
python3 main.py
```

## Guidelines

- Keep GTK widgets and future service/API logic in separate modules as the project grows.
- Prefer GTK/libadwaita widgets and theme-aware styling over hard-coded colors.
- Never commit access tokens, passwords, or personal AniList credentials.
- Explain how you tested UI or service changes in your pull request.

## Commit messages

Use the Conventional Commits format:

```text
<type>(<optional scope>): <imperative summary>
```

Common types:
- `feat`: add user-facing functionality
- `fix`: correct a bug
- `test`: add or update tests
- `refactor`: restructure code without changing behavior
- `docs`: documentation-only changes
- `build`: packaging or build-system changes
- `ci`: continuous-integration changes
- `chore`: maintenance that does not fit another type

Examples:

```text
fix(storage): validate edits by database ID
test(storage): cover duplicate catalogue identities
ci: compile Python sources before tests
docs: document development setup
```

Use a short, specific, imperative summary. Keep unrelated changes in separate commits. Before committing, run the relevant tests; after pushing, check the CI result and fix failures before continuing.
