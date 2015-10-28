## Last working clone of dired, provided by the developer (who has removed the original repo).

Forks and/or PRs are welcome, I'm not the developer of this project.

# Sublime Text dired

A Sublime Text 3 plugin that displays a directory in a view, allowing easy file manipulation,
loosely copied from emacs dired mode.

## Installation

You can install via [Sublime Package Control](http://wbond.net/sublime_packages/package_control)
Or you can clone this repo into your *Sublime Text 3/Packages*

## Using

The plugin provides a `dired` command which allows you to choose a directory to display.  The
files in the directory are displayed in a list allowing them to be moved, renamed, or deleted.

There is no default binding for the dired command itself, but once in a dired view the
following are available:

* `u` - up to parent
* `n` - move to next file
* `p` - move to previous file
* `D` - delete files
* `M` - move files
* `R` - rename files
* `r` - refresh
* `m` - toggle mark
* `U` - unmark all files
* `t` - toggle all marks
* `*.` - mark by file extension
* `Enter` - open file/directory
* `Ctrl/Alt/Cmd+Enter` - open file/directory in new view

If there are marked files, operations only affect those files.  Otherwise files in selections
or with cursors on them are affected.  This works nicely with multiple cursors and selections.

### Rename

The rename command puts the view into "rename mode".  The view is made editable so files can be
renamed directly in the view using all of your Sublime Text tools: multiple cursors, search and
replace, etc.

Use `Ctrl+Enter` to commit your changes and `Ctrl+Escape` to cancel them.

Rename compares the names before and after editing, so you must not add or remove lines.

## Settings

### reuse_view

If True, the default, pressing Enter on a directory uses the current view.  If False, a new
view is created.

If only one directory is selected, Cmd/Ctrl/Alt+Enter can be used to force a new view even when
reuse_view is set.

### omit_patterns

Array of regular expressions matching filenames excluded from directory listing. Note that
regexps are written as strings, so escape sequences must be doubled, i.e. `"\\."` for `/\./` regexp.

By default empty, displaying all files. To hide unix dot files, you can use
```
{
  "omit_patterns": "^\\."
}
```