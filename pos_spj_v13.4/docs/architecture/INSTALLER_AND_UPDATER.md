# Installer and Updater Rules

## Goal

The desktop PyQt application must be installable as a Windows `.exe` and prepared for safe version updates.

## Persistent data

Persistent data must live in user data directories resolved through `AppPaths`. Do not rely on loose relative paths for databases, backups, logs, manifests, downloads, or generated files.

## Read-only bundled resources

`AppPaths.root` remains the source package root or the directory containing the
installed executable. `AppPaths.resource_root` locates bundled artwork separately:

- Source checkout: the real package root, independent of the working directory.
- Frozen PyInstaller bundle: `sys._MEIPASS`, including a one-file extraction
  directory or a one-folder bundle's internal resource directory.
- Frozen installation without an extraction directory: `AppPaths.root`.

This follows PyInstaller's documented distinction between the executable and
bundled data locations. [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html).

Tests and embedded hosts can inject `resource_dir` independently of `base_dir`
and `data_dir`. An explicit `base_dir` alone describes a complete installation,
so resources use that directory unless `resource_dir` is also supplied.
`AppPaths.from_environment()` captures all three locations. Bundled resources
are read-only; `ensure_directories()` creates only persistent data directories.

Official JUANIS artwork must be included at `assets/branding/` relative to
`resource_root`, with these identifiers and supported SVG, PNG or ICO extensions:

```text
logo_horizontal_light
logo_horizontal_dark
isotype_light
isotype_dark
app_icon
window_icon
```

When packaging is added, the PyInstaller `Analysis.datas` entry must preserve
that destination, for example `(str(branding_source), "assets/branding")`, where
`branding_source` is the absolute path to the real package's approved artwork
directory. Data files require explicit inclusion in the bundle.
[PyInstaller data files](https://pyinstaller.org/en/stable/spec-files.html#adding-data-files).

The inspected repository currently has no official JUANIS artwork and no
PyInstaller specification or installer build pipeline. This resource contract
and simulated bundle tests do not constitute a verified executable build.
Only approved artwork may populate this directory; generic web icons, product
images and generated placeholders are not substitutes for the JUANIS identity.

## SQLite backup before update

Before applying a version update, the updater must create an automatic SQLite backup. The backup process must be explicit, logged, and recoverable.

## Update flow

A safe update flow should include:

1. Detect current version.
2. Download or read update manifest.
3. Validate manifest and package integrity.
4. Create SQLite backup.
5. Apply update.
6. Validate startup or migration state.
7. Provide rollback or restore instructions when possible.

## Migration discipline

Installer and updater code must not apply ad-hoc schema changes outside the migration system. Schema changes must remain in `migrations/`.

## Future API compatibility

Updater and installer infrastructure must not duplicate business logic. Desktop and future API clients should continue to share backend use cases.
