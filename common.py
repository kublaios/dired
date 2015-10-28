
import re
from sublime import Region

RE_FILE = re.compile(r'^([^\\// ].*)$')

def first(seq, pred):
    # I can't comprehend how this isn't built-in.
    return next((item for item in seq if pred(item)), None)

class DiredBaseCommand:
    """
    Convenience functions for dired TextCommands
    """
    @property
    def path(self):
        return self.view.settings().get('dired_path')

    def filecount(self):
        """
        Returns the number of files and directories in the view.
        """
        return self.view.settings().get('dired_count', 0)

    def move(self, forward=None):
        """
        Moves the cursor one line forward or backwards.  Clears all sections.
        """
        assert forward in (True, False), 'forward must be set to True or False'

        files = self.fileregion()
        if files.empty():
            return

        pt = self.view.sel()[0].a

        if files.contains(pt):
            # Try moving by one line.
            line = self.view.line(pt)
            pt = forward and (line.b + 1) or (line.a - 1)

        if not files.contains(pt):
            # Not (or no longer) in the list of files, so move to the closest edge.
            pt = (pt > files.b) and files.b or files.a

        line = self.view.line(pt)
        self.view.sel().clear()
        self.view.sel().add(Region(line.a, line.a))


    def fileregion(self):
        """
        Returns a region containing the lines containing filenames.  If there are no filenames
        Region(0,0) is returned.
        """
        count = self.filecount()
        if count == 0:
            return Region(0, 0)
        return Region(self.view.text_point(2, 0), self.view.text_point(count+2, 0)-1)


    def get_all(self):
        """
        Returns a list of all filenames in the view.
        """
        return [ RE_FILE.match(self.view.substr(l)).group(1) for l in self.view.lines(self.fileregion()) ]


    def get_selected(self):
        """
        Returns a list of selected filenames.
        """
        names = set()
        fileregion = self.fileregion()
        for sel in self.view.sel():
            lines = self.view.lines(sel)
            for line in lines:
                if fileregion.contains(line):
                    text = self.view.substr(line)
                    names.add(RE_FILE.match(text).group(1))
        return sorted(list(names))

    def get_marked(self):
        lines = []
        if self.filecount():
            for region in self.view.get_regions('marked'):
                lines.extend(self.view.lines(region))
        return [ RE_FILE.match(self.view.substr(line)).group(1) for line in lines ]

    def _mark(self, mark=None, regions=None):
        """
        Marks the requested files.

        mark
            True, False, or a function with signature `func(oldmark, filename)`.  The function
            should return True or False.

        regions
            Either a single region or a sequence of regions.  Only files within the region will
            be modified.
        """
        # Allow the user to pass a single region or a collection (like view.sel()).
        if isinstance(regions, Region):
            regions = [ regions ]

        filergn = self.fileregion()

        # We can't update regions for a key, only replace, so we need to record the existing
        # marks.
        previous = self.view.get_regions('marked')
        marked = { RE_FILE.match(self.view.substr(r)).group(1): r for r in previous }

        for region in regions:
            for line in self.view.lines(region):
                if filergn.contains(line):
                    text = self.view.substr(line)
                    filename = RE_FILE.match(text).group(1)

                    if mark not in (True, False):
                        newmark = mark(filename in marked, filename)
                        assert newmark in (True, False), 'Invalid mark: {}'.format(newmark)
                    else:
                        newmark = mark

                    if newmark:
                        marked[filename] = line
                    else:
                        marked.pop(filename, None)

        if marked:
            r = sorted(list(marked.values()), key=lambda region: region.a)
            self.view.add_regions('marked', r, 'dired.marked', 'dot', 0)
        else:
            self.view.erase_regions('marked')


    def set_help_text(self, edit, text):
        # There is only 1 help text area, but the scope selector will skip blank lines
        # so use the union of all of the regions.
        regions = self.view.find_by_selector('comment.dired.help')
        region = regions[0]
        for other in regions[1:]:
            region = region.cover(other)
        start = region.begin()
        self.view.erase(edit, region)
        self.view.insert(edit, start, text)
