from cms import dbutil, diffutil, htmlutil
from cms.dateutil import utcnow
from pyramid.security import authenticated_userid
from cms.thirdparty import diff_match_patch

dmp = diff_match_patch.diff_match_patch()

class HistoryCollection(object):

    def __init__(self, request):
        self.request = request
        self._collection_name = "history"

    def _get_collection(self):
        return dbutil.get_collection(self.request, self._collection_name)

    def log_history(self, action, ids, **kwargs):
        doc = dict(
            time = utcnow(),
            user = authenticated_userid(self.request),
            action = action,
            ids = ids,
        )
        doc.update(**kwargs)
        self._get_collection().save(doc, safe=True)

    def get_history(self, spec=None, sort=None, skip=0, limit=0):
        cursor = self._get_collection().find(spec=spec, sort=sort, skip=skip, limit=limit)
        total = cursor.count()
        return dict(total=total, items=list(cursor))

    def get_history_for_id(self, _id, skip=0, limit=20):
        return self.get_history(spec={'ids':_id}, sort=[('time', -1)], skip=skip, limit=limit)

    def get_history_for_user(self, username, skip=0, limit=20):
        return self.get_history(spec={'user':username}, sort=[('time', -1)], skip=skip, limit=limit)

    def get_history_item(self, _id):
        return self._get_collection().find_one(dict(_id=_id))

    def apply_history(self, obj, history_id):
        """ Given a content object and the _id of a history record, apply
        changes from the edit history such that the object has the schema
        values it had just after the specified history event.
        Note that this method modifies the content object in place.
        """
        patches = []
        for history in self.get_history_for_id(obj._id)['items']:
            if history['_id'] == history_id:
                data = diffutil.patch_dictionary_multi(obj.get_schema_values(), patches)
                obj.update(**data)
                return
            if history['action'] not in ('edit', 'revert'): continue
            patch = history['changes']
            if patch: patches.append(patch)
        raise ValueError("Didn't find specified history record.")

    def get_history_diffs(self, obj, history_id1, history_id2=None, after_earlier_event=True):
        """ Given a content object and the _ids of one or two history records, return a dictionary 
        of the schema values that changed between history_id1 and history_id2.
        If history_id2 is None, use the current/latest version of the content object.
        Note that if two history ids are specified, 1 need not be chronologically before 2.
        Note also that in general the schema values considered are those just after each
        history event occurred.  The parameter after_earlier_event can be set to False if instead you
        want to consider the values just before the earlier of the two history events.
        (This is particularly handy when the same history ID is passed for both history_id1 and history_id2;
        in such a case, you would get the changes made for that single edit event.)

        The keys are schema names.  The values are dictionaries with the keys: "before" and "after".
        If the values are strings, there's also a key "diff" which contains an html fragment
        highlighting the diffs with <ins> and <del> tags.

#        Further, if at least one of the strings appears to contain html, there's also a key "htmldiff"
#        which contains another html fragment highlighting the diffs with <ins> and <del> tags, only this 
#        time a special differ was used that ignores html markup.
#
#        Practically speaking, if there's an "htmldiff" key in the result, it means that the before
#        and after values contain HTML; the "htmldiff" shows differences in the rendered html,
#        while "diff" shows differences in the source html.
        """
        if (history_id1 == history_id2) and after_earlier_event: return {}  # Nothing could have changed in this case.
        after = before = None
        history_ids = [history_id1]
        if history_id2:
            history_ids.append(history_id2)
        else:
            after = obj.get_schema_values()
        patches = []
        for history in self.get_history_for_id(obj._id)['items']:
            if history['_id'] in history_ids:
                if after:
                    if after_earlier_event:
                        before = diffutil.patch_dictionary_multi(after, patches)
                        return diff_dictionaries(before, after)
                else:
                    after = diffutil.patch_dictionary_multi(obj.get_schema_values(), patches)
                    patches = []

            if history['action'] in ('edit', 'revert'):
                patch = history['changes']
                if patch: patches.append(patch)

            if history['_id'] in history_ids:
                if after and not after_earlier_event:
                    before = diffutil.patch_dictionary_multi(after, patches)
                    return diff_dictionaries(before, after)

        raise ValueError("Didn't find specified history record.")

    def get_edit_history_diffs(self, obj, history_id):
        return self.get_history_diffs(obj, history_id, history_id, after_earlier_event=False)

    def get_history_subitem_for_child_id(self, history_item, child_id):
        """ Certain history items (ones that deal with multiple children) have a list
        of data about the affected children.  By convention, this list has the name "children"
        and each item has a key "id".
        This method tries to return the subitem from that list for the specified child_id.
        """
        children = history_item.get('children', [])
        for subitem in children:
            if subitem.get('id') == child_id:
                return subitem
        return None

# FIXME: produce better output...
def diff_dictionaries(before, after):
    result = {}
    for name in after.keys():
        b = before[name]
        a = after[name]
        if a == b: continue
        result_item = dict(before=b, after=a)
        result[name] = result_item
        if (type(a) in (str, unicode)) and (type(b) in (str, unicode)):
            result_item['diff'] = diffutil.pretty_text_diff(b, a)
# FIXME: html differ is kinda crappy (too many false positives) and maybe isn't so useful anyway, 
#        given that we can't see changes to attribute values with it.
#            if htmlutil.sniff_html(a) or htmlutil.sniff_html(b):
#                result_item['htmldiff'] = diffutil.pretty_html_diff(b, a)

# FIXME: on the other hand, pretty_html_diff might be useful on other (non-html) data, such as lists, files, etc
# if they are somehow converted into an html presentation first.
# For example, a list of files could be rendered as a <ul> where each item has data about each file... then
# the two html fragments could be diffed.
    return result
