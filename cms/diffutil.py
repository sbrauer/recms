from thirdparty import diff_match_patch, htmldiff
import copy

dmp = diff_match_patch.diff_match_patch()

def pretty_text_diff(text1, text2):
    """ Returns an html fragment showing the differences between two pieces of plain text.
    Differences are marked up with <ins> and <del> elements with class="diff".
    """
    diffs = dmp.diff_main(text1, text2)
    dmp.diff_cleanupSemantic(diffs)
    result = []
    for (op, data) in diffs:
      text = (data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n","<br />"))
      if op == dmp.DIFF_INSERT:
        result.append('<ins class="diff">%s</ins>' % text)
      elif op == dmp.DIFF_DELETE:
        result.append('<del class="diff">%s</del>' % text)
      elif op == dmp.DIFF_EQUAL:
        result.append(text)
    return "".join(result)

class MyHTMLMatcher(htmldiff.NoTagHTMLMatcher):
    def startInsertText(self):
        return '<ins class="diff">'
    def endInsertText(self):
        return '</ins>'
    def startDeleteText(self):
        return '<del class="diff">'
    def endDeleteText(self):
        return '</del>'

def pretty_html_diff(html1, html2):
    """ Returns an html fragment showing the differences between two html fragments.
    Differences are marked up with <ins> and <del> elements with class="diff".
    """
    h = MyHTMLMatcher(html1, html2)
    return h.htmlDiff()

###################################################################
# Various functions to handle diffing of deeply nested dictionaries
###################################################################

def flatten_dictionary(d, prefix=''):
    flattened = {}
    for (name, value) in d.items():
        if prefix:
            key = "%s.%s" % (prefix, name)
        else:
            key = "%s" % name
        if type(value) == tuple:
            value = list(value)
        if type(value) == list:
            flattened.update(_flatten_list(value, key))
        elif type(value) == dict:
            flattened.update(flatten_dictionary(value, key))
        else:
            flattened[str(key)] = value
    return flattened

def _flatten_list(l, prefix=''):
    flattened = {}
    flattened["%s.__len__" % prefix] = len(l) # Will be handy for patches.
    for (i, value) in enumerate(l):
        key = "%s[%s]" % (prefix, i)
        if type(value) == tuple:
            value = list(value)
        if type(value) == list:
            flattened.update(_flatten_list(value, key))
        elif type(value) == dict:
            flattened.update(flatten_dictionary(value, key))
        else:
            flattened[str(key)] = value
    return flattened

def unflatten_dictionary(fd):
    # Note that this function does not handle lists of lists.
    # It's fine with any other nesting though:
    # - dictonaries of dictonaries
    # - dictonaries of lists
    # - lists of dictionaries
    unflattened = {}
    for (name, value) in fd.items():
        curr_dict = unflattened
        curr_list = None
        name_parts = name.split('.')
        for (i, np) in enumerate(name_parts):
            is_last_part = (i+1) == len(name_parts)

            if '[' in np:
                # Current name part refers to a list.
                bracket_idx = np.index('[')
                list_name = np[:bracket_idx]
                list_idx = int(np[bracket_idx+1:-1])
                curr_list = curr_dict.get(list_name, [])
                curr_dict[list_name] = curr_list

                # Grow the list if necessary.
                missing = list_idx + 1 - len(curr_list)
                while missing > 0:
                    curr_list.append({})
                    missing -= 1

                if is_last_part:
                    curr_list[list_idx] = value
                else:
                    curr_dict = curr_list[list_idx]
            elif (not is_last_part) and (name_parts[i+1] == '__len__'):
                if value==0:
                    # Handle empty lists.
                    curr_dict[np] = []
                    # Note that non-empty list will be created as we encounter their children.
                break
            else:
                # Current name part refers to a dictionary key.
                if is_last_part:
                    curr_dict[np] = value
                else:
                    if not curr_dict.has_key(np):
                        curr_dict[np] = {}
                    curr_dict = curr_dict[np]
    return unflattened

def diff_flattened_dictionaries(fd1, fd2):
    """ Returns a patch (a list of name-value tuples) that can be passed to
    patch_flattened_dictionary() or patch_dictionary().
    fd1 = the "before" values
    fd2 = the "after" values
    The returned patch can be applied to fd2 to obtain fd1.
    """
    changes = []
    for key in fd1.keys():
        old = fd1.get(key, None)
        new = fd2.get(key, None)
        if old != new:
            change = old
            if (type(old)==str and type(new)==str) or (type(old)==unicode and type(new)==unicode):
                # Compute a patch.  If the patch is smaller than the old value, save the patch instead.
                # Note: All patches will start with "@@ ".
                # Code that reconstructs old versions of edited objects can check
                # for this prefix to decide whether the stored change is a patch or the old string.
                try:
                    patch = dmp.patch_toText(dmp.patch_make(new, old))
                    if len(patch) < len(old):
                        change = patch
                except:
                    pass
            changes.append((key, change))
    return changes

def patch_flattened_dictionary(fd, patch):
    patched = copy.copy(fd)
    lengths = {}
    for (name, value) in patch:
        if name.endswith('__len__'):
            listname = name[:-8]
            lengths[listname] = value
        else:
            if type(value) in (str, unicode) and value.startswith('@@ '):
                # Apply patch
                current = patched.get(name, '')
                value = dmp.patch_apply(dmp.patch_fromText(value), current)[0]
        patched[name] = value

    # Shorten lists (as needed):
    for (listname, length) in lengths.items():
        prefix = listname+'['
        names_to_del = []
        for (name, value) in patched.items():
            if name.startswith(prefix):
                tmp = name[len(prefix):]
                bracket_idx = tmp.index(']')
                list_idx = int(tmp[:bracket_idx])
                if list_idx >= length:
                    names_to_del.append(name)
        for name in names_to_del:
            del patched[name]
    return patched

def diff_dictionaries(d1, d2):
    """ Returns a patch (a list of name-value tuples) that can be passed to
    patch_flattened_dictionary() or patch_dictionary().
    d1 = the "before" values
    d2 = the "after" values
    The returned patch can be applied to d2 to obtain d1.
    """
    return diff_flattened_dictionaries(flatten_dictionary(d1), flatten_dictionary(d2))

def patch_dictionary(d, patch):
    return unflatten_dictionary(patch_flattened_dictionary(flatten_dictionary(d), patch))

def patch_dictionary_multi(d, patches):
    f = flatten_dictionary(d)
    for patch in patches:
        f = patch_flattened_dictionary(f, patch)
    return unflatten_dictionary(f)

def get_patch_keys(patch, top_level_only=False):
    """ Returns a list of the "keys" in a patch.
    (Handy on the history view page to list what changed.)
    """
    keys = set()
    for (key, value) in patch:
        if top_level_only:
            key = key.split('.')[0]
            if '[' in key:
                bracket_idx = key.index('[')
                key = key[:bracket_idx]
        keys.add(key)
    return keys
