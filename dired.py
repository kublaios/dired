
import sublime
from sublime import Region
from sublime_plugin import WindowCommand, TextCommand
import os, shutil, tempfile, re
from os.path import basename, dirname, isdir, exists, join, isabs, normpath

from .common import RE_FILE, DiredBaseCommand
from . import prompt
from .show import show

# Each dired view stores its path in its local settings as 'dired_path'.

NORMAL_HELP = """\
 m = toggle mark
 t = toggle all marks
 U = unmark all
 *. = mark by file extension

 Enter/o = Open file / view directory
 R = rename
 M = move
 D = delete
 cd = create directory
 cf = create file

 u = up to parent directory
 g = goto directory
 p = move to previous file
 n = move to next file
 r = refresh view

 B = Goto Anywhere(goto any directory, bookmark or project dir)
 ab = add to bookmark
 ap = add to project
 rb = remove from bookmark
 ra = remove from project

 P = toggle preview mode on/off

 j = jump to file/dir name """

RENAME_HELP = """\
 Rename files by editing them directly, then:
 Ctrl+Enter = apply changes
 Ctrl+Escape = discard changes"""


def reuse_view():
    return sublime.load_settings('dired.sublime-settings').get('reuse_view', False)

def omit_patterns():
    return sublime.load_settings('dired.sublime-settings').get('omit_patterns', [])


class DiredCommand(WindowCommand):
    """
    Prompt for a directory to display and display it.
    """
    def run(self):
        prompt.start('Directory:', self.window, self._determine_path(), self._show)

    def _show(self, path):
        show(self.window, path)

    def _determine_path(self):
        # Use the current view's directory if it has one.
        view = self.window.active_view()
        path = view and view.file_name()
        if path:
            return dirname(path)

        # Use the first project folder if there is one.
        data = self.window.project_data()
        if data and 'folders' in data:
            folders = data['folders']
            if folders:
                return folders[0]['path']

        # Use the user's home directory.
        return os.path.expanduser('~')

class DiredRefreshCommand(TextCommand, DiredBaseCommand):
    """
    Populates or repopulates a dired view.
    """
    def run(self, edit, goto=None):
        """
        goto
            Optional filename to put the cursor on.
        """
        path = self.path

        names = os.listdir(path)
        names.sort()
        f = []
        for name in names:
            if self.is_omitted(name):
                continue
            if isdir(join(path, name)):
                name += os.sep
            f.append(name)

        marked = set(self.get_marked())

        text = [ path ]
        text.append('')
        text.extend(f)
        text.append('')
        text.append(NORMAL_HELP)

        self.view.set_read_only(False)

        self.view.erase(edit, Region(0, self.view.size()))
        self.view.insert(edit, 0, '\n'.join(text))
        self.view.set_syntax_file('Packages/dired/dired.tmLanguage')
        self.view.settings().set('dired_count', len(f))

        if marked:
            # Even if we have the same filenames, they may have moved so we have to manually
            # find them again.
            regions = []
            for line in self.view.lines(self.fileregion()):
                filename = RE_FILE.match(self.view.substr(line)).group(1)
                if filename in marked:
                    regions.append(line)
            self.view.add_regions('marked', regions, 'dired.marked', 'dot', 0)
        else:
            self.view.erase_regions('marked')

        self.view.set_read_only(True)

        # Place the cursor.
        if f:
            pt = self.fileregion().a
            if goto:
                if isdir(join(path, goto)) and not goto.endswith(os.sep):
                    goto += os.sep
                try:
                    line = f.index(goto) + 2
                    pt = self.view.text_point(line, 0)
                except ValueError:
                    pass

            self.view.sel().clear()
            self.view.sel().add(Region(pt, pt))

    def is_omitted(self, name):
        for pattern in omit_patterns():
            if re.match(pattern, name):
                return True
        return False


class DiredNextLineCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, forward=None):
        self.move(forward)


class DiredSelect(TextCommand, DiredBaseCommand):
    def run(self, edit, new_view=False):
        path = self.path
        filenames = self.get_selected()

        # If reuse view is turned on and the only item is a directory, refresh the existing view.
        if not new_view and reuse_view():
            if len(filenames) == 1 and isdir(join(path, filenames[0])):
                fqn = join(path, filenames[0])
                show(self.view.window(), fqn, view_id=self.view.id())
                return

        for filename in filenames:
            fqn = join(path, filename)
            if isdir(fqn):
                show(self.view.window(), fqn, ignore_existing=new_view)
            else:
                self.view.window().open_file(fqn)


class DiredCreateCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, which=None):
        assert which in ('file', 'directory'), "which: " + which

        # Is there a better way to do this?  Why isn't there some kind of context?  I assume
        # the command instance is global and really shouldn't have instance information.
        callback = getattr(self, 'on_done_' + which, None)
        self.view.window().show_input_panel(which.capitalize() + ':', '', callback, None, None)

    def on_done_file(self, value):
        self._on_done('file', value)

    def on_done_directory(self, value):
        self._on_done('directory', value)

    def _on_done(self, which, value):
        value = value.strip()
        if not value:
            return

        fqn = join(self.path, value)
        if exists(fqn):
            sublime.error_message('{} already exists'.format(fqn))
            return

        if which == 'directory':
            os.makedirs(fqn)
        else:
            open(fqn, 'wb')

        self.view.run_command('dired_refresh', {'goto': value})


class DiredMarkExtensionCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, ext=None):
        filergn = self.fileregion()
        if filergn.empty():
            return

        if ext is None:
            # This is the first time we've been called, so ask for the extension.
            self.view.window().show_input_panel('Extension:', '', self.on_done, None, None)
        else:
            # We have already asked for the extension but had to re-run the command to get an
            # edit object.  (Sublime's command design really sucks.)
            def _markfunc(oldmark, filename):
                return filename.endswith(ext) and True or oldmark
            self._mark(mark=_markfunc, regions=self.fileregion())

    def on_done(self, ext):
        ext = ext.strip()
        if not ext:
            return
        if not ext.startswith('.'):
            ext = '.' + ext
        self.view.run_command('dired_mark_extension', { 'ext': ext })

class DiredMarkCommand(TextCommand, DiredBaseCommand):
    """
    Marks or unmarks files.

    The mark can be set to '*' to mark a file, ' ' to unmark a file,  or 't' to toggle the
    mark.

    By default only selected files are marked, but if markall is True all files are
    marked/unmarked and the selection is ignored.

    If there is no selection and mark is '*', the cursor is moved to the next line so
    successive files can be marked by repeating the mark key binding (e.g. 'm').
    """
    def run(self, edit, mark=True, markall=False):
        assert mark in (True, False, 'toggle')

        filergn = self.fileregion()
        if filergn.empty():
            return

        # If markall is set, mark/unmark all files.  Otherwise only those that are selected.
        if markall:
            regions = [ filergn ]
        else:
            regions = self.view.sel()

        def _toggle(oldmark, filename):
            return not oldmark
        if mark == 'toggle':
            # Special internal case.
            mark = _toggle

        self._mark(mark=mark, regions=regions)

        # If there is no selection, move the cursor forward so the user can keep pressing 'm'
        # to mark successive files.
        if not markall and len(self.view.sel()) == 1 and self.view.sel()[0].empty():
            self.move(True)


class DiredDeleteCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        files = self.get_marked() or self.get_selected()
        if files:
            # Yes, I know this is English.  Not sure how Sublime is translating.
            if len(files) == 1:
                msg = "Delete {}?".format(files[0])
            else:
                msg = "Delete {} items?".format(len(files))
            if sublime.ok_cancel_dialog(msg):
                for filename in files:
                    fqn = join(self.path, filename)
                    if isdir(fqn):
                        shutil.rmtree(fqn)
                    else:
                        os.remove(fqn)
                self.view.run_command('dired_refresh')


class DiredMoveCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        files = self.get_marked() or self.get_selected()
        if files:
            prompt.start('Move to:', self.view.window(), self.path, self._move)

    def _move(self, path):
        if path == self.path:
            return

        files = self.get_marked() or self.get_selected()

        if not isabs(path):
            path = join(self.path, path)
        if not isdir(path):
            sublime.error_message('Not a valid directory: {}'.format(path))
            return

        # Move all items into the target directory.  If the target directory was also selected,
        # ignore it.
        files = self.get_marked() or self.get_selected()
        path = normpath(path)
        for filename in files:
            fqn = normpath(join(self.path, filename))
            if fqn != path:
                shutil.move(fqn, path)
        self.view.run_command('dired_refresh')


class DiredRenameCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if self.filecount():
            # Store the original filenames so we can compare later.
            self.view.settings().set('rename', self.get_all())
            self.view.settings().set('dired_rename_mode', True)
            self.view.set_read_only(False)
            self.set_help_text(edit, RENAME_HELP)

            # Mark the original filename lines so we can make sure they are in the same
            # place.
            r = self.fileregion()
            self.view.add_regions('rename', [ r ], '', '', 0)


class DiredRenameCancelCommand(TextCommand, DiredBaseCommand):
    """
    Cancel rename mode.
    """
    def run(self, edit):
        self.view.settings().erase('rename')
        self.view.settings().set('dired_rename_mode', False)
        self.view.run_command('dired_refresh')


class RenameError(Exception):
    pass


class DiredRenameCommitCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if not self.view.settings().has('rename'):
            # Shouldn't happen, but we want to cleanup when things go wrong.
            self.view.run_command('dired_refresh')
            return

        before = self.view.settings().get('rename')

        # We marked the set of files with a region.  Make sure the region still has the same
        # number of files.
        after = []

        for region in self.view.get_regions('rename'):
            for line in self.view.lines(region):
                after.append(self.view.substr(line).strip())

        if len(after) != len(before):
            sublime.error_message('You cannot add or remove lines')
            return

        if len(set(after)) != len(after):
            sublime.error_message('There are duplicate filenames')
            return

        diffs = [ (b, a) for (b, a) in zip(before, after) if b != a ]
        if diffs:
            existing = set(before)
            while diffs:
                b, a = diffs.pop(0)

                if a in existing:
                    # There is already a file with this name.  Give it a temporary name (in
                    # case of cycles like "x->z and z->x") and put it back on the list.
                    tmp = tempfile.NamedTemporaryFile(delete=False, dir=self.path).name
                    os.unlink(tmp)
                    diffs.append((tmp, a))
                    a = tmp

                print('dired rename: {} --> {}'.format(b, a))
                os.rename(join(self.path, b), join(self.path, a))
                existing.remove(b)
                existing.add(a)

        self.view.erase_regions('rename')
        self.view.settings().erase('rename')
        self.view.settings().set('dired_rename_mode', False)
        self.view.run_command('dired_refresh')


class DiredUpCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        parent = dirname(self.path.rstrip(os.sep)) + os.sep
        if parent == self.path:
            return

        view_id = (self.view.id() if reuse_view() else None)
        show(self.view.window(), parent, view_id, goto=basename(self.path.rstrip(os.sep)))


class DiredGotoCommand(TextCommand, DiredBaseCommand):
    """
    Prompt for a new directory.
    """
    def run(self, edit):
        prompt.start('Goto:', self.view.window(), self.path, self.goto)

    def goto(self, path):
        show(self.view.window(), path, view_id=self.view.id())


from sublime_plugin import EventListener
from .common import first


def groups_on_preview(window) :
    """
    Retrun group number of dired(active) and preview.
    """
    groups = window.num_groups()
    active_group = window.active_group()

    # Usually, preview group is made the right side of dired(active) group.
    if active_group < groups - 1 or groups == 1 :
        return [active_group, active_group + 1]

    # If the dired(active) group is the rightmost of window,
    # preview group is made the left side of it.
    else :
        return [active_group, active_group - 1]


class DiredPreviewCommand(TextCommand, DiredBaseCommand):
    """
    Toggle the preview mode and set the groups.
    """
    def run(self, edit):
        window = self.view.window()
        preview_id = self.view.settings().get('preview_id')
        preview_view = first(window.views(), lambda v: v.id() == preview_id)

        # Preview mode on.
        if not 'Preview: ' in self.view.name()[0:9] :
            if not self.view.settings().get('preview_key') :
                self.view.settings().set('preview_key', True)

                # If user clicked in dired(active) view when he/she was previewing
                # a directory, it remain the preview view but preview_key become
                # "False". This code is to close the remained preview view.
                if preview_view :
                    window.run_command('dired_preview_close')

                self.view.settings().set('initial_group', window.num_groups())
                if self.view.settings().get('initial_group') == 1 :
                    window.run_command("set_layout", {"cols": [0.0, 0.5, 1.0], "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]})
                    window.focus_group(0)

                path_list = get_path_list(self.path, self.get_selected(), False)

                if path_list :
                    window.run_command('dired_preview_refresh', {'path':path_list[0]})

            # Preview mode off.
            else :
                window.run_command('dired_preview_close')
                self.view.settings().set('preview_key', False)


class DiredPreviewCloseCommand(TextCommand, DiredBaseCommand):
    """
    Close preview view.
    """
    def run(self, edit):
        window = self.view.window()

        # Close preview without closing editting file/s.
        groups = groups_on_preview(window)

        # Get directory preview view.
        preview_id = self.view.settings().get('preview_id')
        preview_view = first(window.views(), lambda v: v.id() == preview_id)
        window.focus_group(groups[1])

        # For image file preview.
        if isinstance(preview_view, type(None)):
            if not window.active_view() :
                window.run_command('close_file')
            else :
                preview_view = window.active_view()

        # For directory and text/binary file preview.
        if preview_view :
            if preview_view.is_scratch() :
                window.focus_view(preview_view)
                preview_view.window().run_command('close_file')

        # Reset to the initial group.
        if self.view.settings().get('initial_group') == 1 :
            window.run_command("set_layout", {"cols": [0.0, 1.0],"rows": [0.0, 1.0],"cells": [[0, 0, 1, 1]]})
        else :
            window.focus_group(groups[0])


class DiredPreviewEventListener(EventListener, DiredBaseCommand):
    def on_selection_modified(self, view):
        self.view = view
        selections = self.view.sel()
        if selections and len(selections) > 0 and 'text.dired' in self.view.scope_name(selections[0].a):
            if self.view.settings().get('preview_key'):
                path_list = get_path_list(self.path, self.get_selected(), False)
                if path_list:
                    self.view.settings().set('preview_key', False)
                    self.view.window().run_command('dired_preview_refresh', {'path':path_list[0]})
                    self.view.settings().set('preview_key', True)


class DiredPreviewRefreshCommand(TextCommand, DiredBaseCommand):
    def run(self, view, path):
        window = self.view.window()
        groups = groups_on_preview(window)
        window.focus_group(groups[1])

        # Get directory preview view.
        preview_id = self.view.settings().get('preview_id')
        preview_view = first(window.views(), lambda v: v.id() == preview_id)


        if os.path.isfile(path):
            if preview_view :
                window.focus_view(preview_view)
                window.run_command('close_file')
            window.open_file(path, sublime.TRANSIENT)
            try :
                window.active_view().set_read_only(True)
                window.active_view().set_scratch(True)
            except :
                pass

        elif os.path.isdir(path):
            if not preview_view :
                show(window, path)
            else :
                show(window, path, view_id=preview_id)
            window.active_view().set_name("Preview: " +  window.active_view().name())
            self.view.settings().set('preview_id' , window.active_view().id())

        window.focus_group(groups[0])


def bookmarks():
    return sublime.load_settings('dired.sublime-settings').get('bookmarks', [])


def project(window) :
    pr = []
    try :
        pr_data = window.project_data()['folders']
        for item in pr_data:
            pr.append(item['path'])
    except :
        pass
    return pr


def get_path_list(path, filenames, dirs_only):
    path_list = []
    if filenames :
        for fn in filenames :
            if dirs_only and os.path.isdir(join(path, fn)) :
                 path_list.append(join(path, fn))
            elif not dirs_only :
                 path_list.append(join(path, fn))
    return path_list


class DiredAddCommand(TextCommand, DiredBaseCommand):
    """
    This command show quick panel to select the selected/marked directories
    or current directory that are/is added to bookmark or project.
    """
    def run(self, edit, target):
        qp_list = []
        path_list = []

        selected_path = get_path_list(self.path, self.get_marked() or self.get_selected(), True)
        current_path = [self.path]

        note = ["Selected dirrectory / Marked directories to " + target, "Current directory to " + target]

        for i, lst in enumerate([selected_path, current_path]) :
            if not len(lst) == 0 :
                qp_list.append([note[i], str(lst)[1:-1].replace('\'', '')])
                path_list.append(lst)

        def on_done(select) :
            if not select == -1 :
                if target == 'bookmark' :
                    cmd = 'dired_add_bookmark'
                elif target == 'project' :
                    cmd = 'dired_add_project'
                self.view.run_command(cmd, {'dirs': path_list[select]})

        self.view.window().show_quick_panel(qp_list, on_done)


class DiredAddProjectCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, dirs):
        for path in dirs :
            if os.path.isdir(path) :
                pr_data = self.view.window().project_data()
                try :
                    pr_data['folders'].append({'follow_symlinks': True, 'path':path})
                except :
                    pr_data = {'folders' : [{'follow_symlinks': True, 'path':path}]}
                self.view.window().set_project_data(pr_data)
                sublime.status_message('Add to this project.')
                self.view.erase_regions('marked')


class DiredRemoveFromProjectCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        pr_data = self.view.window().project_data()
        pr = project(self.view.window())

        def on_done(select) :
            if not select == -1 :
                pr_data['folders'].pop(select)
                self.view.window().set_project_data(pr_data)

        self.view.window().show_quick_panel(pr, on_done)


class DiredAddBookmarkCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, dirs):
        settings = sublime.load_settings('dired.sublime-settings')

        for key_name in ['reuse_view', 'bookmarks']:
            settings.set(key_name, settings.get(key_name))

        bm = bookmarks()
        for path in dirs :
            bm.append(path)
            settings.set('bookmarks', bm)

            # This command makes/writes a sublime-settings file at Packages/User/,
            # and doesn't write into one at Packages/dired/.
            sublime.save_settings('dired.sublime-settings')

            sublime.status_message('Bookmarking succeeded.')
            self.view.erase_regions('marked')


class DiredRemoveBookmarkCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        settings = sublime.load_settings('dired.sublime-settings')

        for key_name in ['reuse_view', 'bookmarks']:
            settings.set(key_name, settings.get(key_name))

        bm = bookmarks()

        def on_done(select) :
            if not select == -1 :
                bm.pop(select)
                sublime.status_message('Remove selected bookmark.')
                settings.set('bookmarks', bm)
                sublime.save_settings('dired.sublime-settings')

        self.view.window().show_quick_panel(bm, on_done)


class DiredGotoAnywhereCommand(TextCommand, DiredCommand):
    """
    This command is to go to a path selected with quick panel.

    The selectable paths are the path of current directory, home, bookmarks,
    project directories and inputted one.

    This was designed to be the alternative to dired and dired_goto command.

    This code is used the code of dired_select command.
    """
    def run(self, edit, new_view=False):
        self.window = self.view.window()
        path = self.view and self.view.file_name()
        home = os.path.expanduser('~')
        bm = bookmarks()
        pr = project(self.window)

        qp_list = []
        if path and new_view :
            qp_list.append('Current dir: ' + os.path.split(path)[0])
        if home :
            qp_list.append('Home: ' + home)
        for item in bm :
            qp_list.append('Bookmark: ' + item)
        for item in pr :
            qp_list.append('Project: ' + item)
        qp_list.append('Goto directory')

        def on_done(select):
            if not select == -1 :
                fqn = qp_list[select]
                if 'Current dir' in fqn :
                    fqn = fqn[13:]
                elif 'Home' in fqn :
                    fqn = fqn[6:]
                elif 'Bookmark' in fqn :
                    fqn = fqn[10:]
                elif 'Project' in fqn :
                    fqn = fqn[9:]
                elif 'Goto directory' in fqn :
                    prompt.start('Directory:', self.window, self._determine_path(), self._show)

                # If reuse view is turned on and the only item is a directory,
                # refresh the existing view.
                if not new_view and reuse_view():
                    if isdir(fqn):
                        show(self.view.window(), fqn, view_id=self.view.id())
                        return

                if isdir(fqn):
                    show(self.view.window(), fqn, ignore_existing=new_view)

        self.view.window().show_quick_panel(qp_list, on_done)


class DiredJumptoNameCommand(TextCommand, DiredBaseCommand):
    """
    Fuzzy-Search file/directory name in current directory.
    """
    def run(self, view):
        path = self.path
        window = self.view.window()
        names = os.listdir(path)
        f = []
        for name in names:
            if isdir(join(path, name)):
                name += os.sep
            f.append(name)

        def on_done(select):
            if not select == -1 :
                line_str = f[select]
                r_list = self.view.find_all(line_str, sublime.LITERAL)

                # Make match whole word.
                if len(r_list) > 1 :
                    for r in r_list :
                        find_str = self.view.substr(self.view.line(r))
                        if find_str == line_str :
                            break
                else :
                    r = r_list[0]

                if self.p_key :
                    window.run_command('dired_preview_refresh', {'path':path + line_str})


                self.view.sel().clear()
                self.view.sel().add(r.a)
                self.view.show(r.a)

                if self.p_key :
                    self.view.settings().set('preview_key', True)

        self.p_key = self.view.settings().get('preview_key')
        self.view.settings().set('preview_key', False)
        window.show_quick_panel(f, on_done)
