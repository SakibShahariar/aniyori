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
