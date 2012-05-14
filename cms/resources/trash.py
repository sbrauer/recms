from folder import unindex_recursively
from collection import Collection
import zope.interface
from interfaces import ITrash
import permissions
from bson.objectid import ObjectId
from pyramid.security import authenticated_userid
from cms.dateutil import utcnow
from cms.exceptions import Veto

class Trash(Collection):
    """ The Trash Collection is a special folder-ish object in the root of the site that behaves
    like the trash or recyclebin that you've seen in various operating systems.
    As an alternative to really deleting content, it can be moved into the trash.
    Once in the trash, it is removed from the fulltext index and has very limited
    permissions (it can be viewed by authenticated users, un-trashed if its parent
    still exists (outside of the trash), or copy/pasted back into the content tree).

    Another key difference between the Trash Collection and a regular Collection is that the 
    Mongo _id (as a string) is used to traverse to items in the trash, instead of __name__.
    This is because there can be several items in the trash with the same __name__.
    """
    zope.interface.implements(ITrash)

    _object_type = "trash"

    def __init__(self, request):
        self.request = request
        self._collection_name = "content"
        self.title = "Trash"
        self.description = "Content can be moved here as an alternative to deleting it forever."
        self.__acl__ = permissions.trash_acl
        self._id = 'trash'
    
    def _morph_spec(self, spec):
        if spec is None: spec = {}
        # Make sure parent is in the spec.
        spec['__parent__'] = self._id
        return spec

    def _get_child_class(self, doc):
        return self.__parent__.get_content_factory(doc['_object_type'])

    def move_child(self, obj):
        if obj.__parent__._id == self._id: return
        orig_parent = obj.__parent__
        orig_name = obj.__name__
        obj._memento = dict(
            orig_name = orig_name,
            orig_parent_id = orig_parent._id,
            orig_parent_path = orig_parent.resource_path(),
            trashed_at = utcnow(),
            trashed_by = authenticated_userid(self.request),
        )
        obj.__parent__ = self
        obj.__name__ = str(obj._id)
        obj.save()  # FIXME: set_modified=False?
        unindex_recursively(obj, include_self=True)
        # Notify old parent that child was moved (gives ordered folders an opportunity to update their ordered name list).
        orig_parent._child_removed(orig_name)
    
    def _child_removed(self, name):
        pass # Like I care?  I'm trash!

    def dememento_child(self, child):
        child.__name__ = child._memento['orig_name']
        del child._memento

    def veto_restore_child(self, child):
        """ Return an error message string if there's any reason why the given child cannot 
        be restored into its original parent.
        Otherwise return None.
        """
        root = self.__parent__
        orig_parent = root.get_content_by_id(child._memento['orig_parent_id'])
        if orig_parent is None: return "Original parent object no longer exists."
        if orig_parent.in_trash(): return "Original parent is also in the trash."
        return orig_parent.veto_add_child(child._memento['orig_name'], child)

    def restore_child(self, child):
        root = self.__parent__
        orig_parent = root.get_content_by_id(child._memento['orig_parent_id'])
        if orig_parent.in_trash(): raise Veto("Original parent is also in the trash.")
        self.dememento_child(child)
        orig_parent.move_child(child)

    def veto_restore_children(self, children):
        """ Return an error message is there is a problem with any of the proposed restores.
        Else return None.
        """
        children_by_parent_id = {}
        for child in children:
            err = self.veto_restore_child(child)
            if err: return "Can't restore child named \"%s\". (%s)" % (child._memento['orig_name'], err)
            parent_id = child._memento['orig_parent_id']
            if not children_by_parent_id.has_key(parent_id):
                children_by_parent_id[parent_id] = []
            children_by_parent_id[parent_id].append(child)
        # Check for items that would be restored to the same folder with the same name...
        for (parent_id, children) in children_by_parent_id.items():
            names = {}
            for child in children:
                child_name = child._memento['orig_name']
                if not names.has_key(child_name):
                    names[child_name] = 0
                names[child_name] += 1
            for (name, count) in names.items():
                if count > 1:
                    return "Can't restore all of the requested objects, since %s would have the non-unique name \"%s\"." % (count, name)
        return None

    def restore_children(self, children):
        error = self.veto_restore_children(children)
        if error: raise Veto(error)
        for child in children:
            self.restore_child(child)
        return len(children)

