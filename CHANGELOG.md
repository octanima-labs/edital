# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.3.0] - 2026-10-21

### Added

- Caller-controlled cancellation for `edit_text()` and `TuiEditor.edit()` through
  an optional `cancel_event`. Integrations can signal the event from another
  thread to discard the draft without confirmation, including during help,
  search, or discard dialogs, and return cancellation after terminal cleanup.
  Pre-cancelled calls validate initial text without opening the UI or requiring
  interactive terminals; finalized outcomes remain stable under late cancellation.
- Embedded cancellation documentation with a socket-watcher integration example
  and guidance on cooperative validation and acceptance races.

### Changed

- Improved API docstrings with previously missing return-type information.

## [0.2.0] - 2026-10-10

### Breaking Changes

- Escape only dismisses the current interaction and no longer exits
  standalone editing or cancels embedded editing. Use Ctrl+Q for explicit exit or
  cancellation, with existing caching/discard rules and modal isolation. Footer
  and help now expose the mode-specific Ctrl+Q action.
- Embedded F3 now validates and accepts the sole document, like F2.
  Find uses F4 in both editors; F3 is not retained as a Find alias.
- Embedded Ctrl+W is reserved instead of deleting a word. Use
  Ctrl+Backspace or Alt+Backspace. Embedded Ctrl+S remains unavailable and does not
  accept or close; Ctrl+A remains line-start navigation and F7 selects all.
- CLI purge of a nonempty cache requires confirmation, defaulting to
  No, or `--force` for unattended use. Empty-cache purge succeeds without a prompt;
  headless `clear_cache()` remains unprompted with no force argument.

### Added

- Multi-tab terminal file editing through the `edital` CLI and headless Python
  file-session APIs, including named and unnamed drafts, explicit save/save-all,
  stable document handles, and tabs that preserve cursor, selection, and undo history.
- Transactional embedded editing through `edit_text()` and `TuiEditor`, with
  synchronous validation, explicit accepted/cancelled outcomes, and caller-owned
  persistence.
- Periodic autosave for previously loaded or explicitly saved files, plus
  entry-scoped recovery snapshots on orderly exit, idempotent restoration,
  conflict detection, and opt-in automatic recovery.
- Validated user YAML configuration with explicit API/CLI overrides, native
  per-user storage locations, and commands for configuration editing and cache
  maintenance.
- Mouse-driven tab closing, independent dirty/conflict markers, configurable
  focus/draft/conflict colors with live updates, and responsive compact dialogs.
- Standalone F8 Documents picker with scrollable session-order rows, tentative
  keyboard browsing, direct activation, Ctrl+W highlighted close with confirmation,
  independent close controls, state
  markers/colors, and highlighted-document reordering with preserved editor state.
- Regex OFF/ON toggle in Find/Replace for both editors, with Python patterns,
  numbered/named replacement captures, zero-width navigation and insertion,
  inline validation errors, and atomic undoable Replace all.
- Shared F5 Find/Replace with literal case-sensitive matching, selected matches,
  current-document Replace all counts, and one-step undo without losing prior history.
- Scrollable F1 keyboard cheatsheets with styled section headings and highlighted
  key combinations in standalone and embedded editing, including
  effective hidden editing bindings and contextual controls above dialogs.
- Ctrl+Shift+PageUp/PageDown tab reordering and headless `EditalSession.move`,
  preserving active identity, cursor, selection, and undo history.
- Purge-specific `-f`/`--force` for skipping CLI cache deletion confirmation.

### Changed

- The footer prioritizes common actions, with complete controls available through F1.
- Recovery choices use “Restore cached version”, “Discard cached version”, and
  “Keep cached version as separate draft”, explaining missing destinations and
  that resolution does not immediately write a file.
- Expanded API docstrings, CLI help, and documentation with pipx/pip installation,
  first-edit and integration examples, upgrade instructions, troubleshooting, and
  a Sphinx API reference generated from source docstrings.

### Fixed

- Save As keeps its prompt, path, and inline diagnostic open on duplicate destinations
  or filesystem failures, permitting correction and retry before F2/F3 continues.
- Rejected recovery resolution preserves snapshots and unsaved documents instead of
  deleting the cached copy before discovering a competing unsaved destination tab.
