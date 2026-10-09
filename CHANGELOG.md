# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Shared F5 Find/Replace with literal case-sensitive matching, selected matches,
  current-document Replace all counts, and one-step undo without losing prior history.
- Scrollable F1 keyboard cheatsheets with styled section headings and highlighted
  key combinations in standalone and embedded editing, including
  effective hidden editing bindings and contextual controls above dialogs.
- Ctrl+Shift+PageUp/PageDown tab reordering and headless `EditalSession.move`,
  preserving active identity, cursor, selection, and undo history. Mouse dragging
  remains deferred.
- Purge-specific `-f`/`--force` for skipping CLI cache deletion confirmation.

### Changed

- **Breaking:** Embedded F3 now validates and accepts the sole document, like F2.
  Find uses F4 in both editors; F3 is not retained as a Find alias.
- **Breaking:** Embedded Ctrl+W is reserved instead of deleting a word. Use
  Ctrl+Backspace or Alt+Backspace. Embedded Ctrl+S remains unavailable and does not
  accept or close; Ctrl+A remains line-start navigation and F7 selects all.
- **Breaking:** CLI purge of a nonempty cache requires confirmation, defaulting to
  No, or `--force` for unattended use. Empty-cache purge succeeds without a prompt;
  headless `clear_cache()` remains unprompted with no force argument.
- The footer prioritizes common actions, with complete controls available through F1.
- Recovery choices use “Restore cached version”, “Discard cached version”, and
  “Keep cached version as separate draft”, explaining missing destinations and
  that resolution does not immediately write a file.

### Fixed

- Save As keeps its prompt, path, and inline diagnostic open on duplicate destinations
  or filesystem failures, permitting correction and retry before F2/F3 continues.
- Rejected recovery resolution preserves snapshots and unsaved documents instead of
  deleting the cached copy before discovering a competing unsaved destination tab.
