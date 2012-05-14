from cms import dbutil
import string
from cms.exceptions import Veto

class Collection(object):
    """ A flat collection (corresponds to a MongoDB collection) of similar Objects,
    each with a unique __name__ value.
    Collection instances are NOT stored as MongoDB documents.
    """

    _object_type = "collection"

    def __init__(self, request, collection_name, child_class):
        """
        collection_name - name of the MongoDB collection
        child_class - the class used to construct children of this collection
        """
        self.request = request
        self._collection_name = collection_name
        self._child_class = child_class

    def _get_collection(self):
        return dbutil.get_collection(self.request, self._collection_name)

    def _get_child_class(self, doc):
        """ doc is a mongodb document from this collection.
        Not used by the base Collection class, but subclasses could
        use it if they store in their documents the class of each child.
        """
        return self._child_class

    def _morph_spec(self, spec):
        """ Can be used to apply a filter to all mongo queries made by this collection.
        """
        # no-op for base Collection class
        return spec

    def has_child(self, name):
        spec = self._morph_spec({'__name__': name})
        doc = self._get_collection().find_one(spec)
        return doc is not None

    def _construct_child_from_mongo_document(self, doc):
        obj = self._get_child_class(doc)(self.request, **(dbutil.encode_keys(doc)))
        obj.__name__ = doc['__name__']
        obj.__parent__ = self
        return obj

    def get_child(self, name):
        spec = self._morph_spec({'__name__': name})
        doc = self._get_collection().find_one(spec)
        if doc is None:
            return None
        return self._construct_child_from_mongo_document(doc)

    def __getitem__(self, name):
        child = self.get_child(name)
        if child is None:
            raise KeyError
        return child

    def get_children_and_total(self, spec=None, sort=None, skip=0, limit=0):
        spec = self._morph_spec(spec)
        cursor = self._get_collection().find(spec=spec, sort=sort, skip=skip, limit=limit)
        total = cursor.count()
        items = []
        for doc in cursor:
            obj = self._construct_child_from_mongo_document(doc)
            items.append(obj)
        return dict(total=total, items=items)

    def get_children(self, spec=None, sort=None, skip=0, limit=0):
        return self.get_children_and_total(spec, sort, skip, limit)['items']

    def get_child_names_and_total(self, spec=None, sort=None, skip=0, limit=0):
        spec = self._morph_spec(spec)
        cursor = self._get_collection().find(spec=spec, fields=['__name__'], sort=sort, skip=skip, limit=limit)
        total = cursor.count()
        items = [r['__name__'] for r in cursor]
        return dict(total=total, items=items)

    def get_child_names(self, spec=None, sort=None, skip=0, limit=0):
        return self.get_child_names_and_total(spec, sort, skip, limit)['items']

    def get_children_lazily(self, spec=None, sort=None):
        """ Return child objects using a generator.
        Great when you want to iterate over a potentially large number of children
        and don't want to load them all into memory at once.
        """
        spec = self._morph_spec(spec)
        cursor = self._get_collection().find(spec=spec, sort=sort)
        for doc in cursor:
            obj = self._construct_child_from_mongo_document(doc)
            yield obj

    # Avoid conflicting with view names.
    RESERVED_NAMES = (
        'add',
        'delete',
        'contents',
        'rename',
        'edit',
        'workflow_transition',
        'history',
        'comment',
        'local_roles',
        'search',
        'object_view',
    )

    ALLOWED_NAME_CHARACTERS = string.letters + string.digits + ".-_ "

    def veto_child_name(self, name, unique=True):
        if name is not None: name = name.strip()
        if not name: return "Name may not be blank."
        if name in self.RESERVED_NAMES: return "\"%s\" is a reserved name." % name
        for ch in name:
            if ch not in self.ALLOWED_NAME_CHARACTERS:
                return "The character \"%s\" is not allowed in names." % ch
        if unique and self.has_child(name): return "The name \"%s\" is already in use." % name
        return None

    def add_child(self, name, child):
        error = self.veto_add_child(name, child)
        if error: raise Veto(error)
        child.__name__ = name
        child.__parent__ = self
        child.save()

    def veto_add_child(self, name, child, unique=True):
        # Return an error message (string) if there's any reason why the specified child can't be added with the specified name.
        # Otherwise return None
        return self.veto_child_name(name, unique)

    def delete_child(self, name):
        child = self.get_child(name)
        if child:
            child._pre_delete()
            self._get_collection().remove(dict(_id=child._id), safe=True)
            return 1
        else:
            return 0

    def rename_child(self, name, newname, _validate=True):
        if name == newname: return 0
        if _validate:
            error = self.veto_child_name(newname)
            if error: raise Veto(error)
        child = self.get_child(name)
        if child:
            child.__name__ = newname
            child.save()
            return 1
        else:
            return 0

    def veto_child_renames(self, renames):
        """ renames is a list of 2-tuples, each containing (old_name, new_name).
        This method will return an error if there is a problem with any of the proposed renames.
        Else returns None.
        """
        new_names = set()
        old_names = set()
        for (old_name, new_name) in renames:
            if old_name == new_name: continue
            error = self.veto_child_name(new_name, unique=False)
            if error: return "Cannot rename \"%s\" to \"%s\". %s" % (old_name, new_name, error)
            # Make sure new_name is unique in this folder, taking into consideration the other proposed renames.
            if new_name in new_names:
                return "The name \"%s\" would not be unique." % new_name
            if (new_name not in old_names) and self.has_child(new_name): return "The name \"%s\" is already in use." % new_name
            old_names.add(old_name)
            new_names.add(new_name)
        return None

    def rename_children(self, renames):
        """ renames is a list of 2-tuples, each containing (old_name, new_name).
        This method will return the number of renames successfully preformed.
        It will validate the proposed renames first and raise an exception if there is any problem.
        """
        error = self.veto_child_renames(renames)
        if error: raise Veto(error)
        count = 0
        for (old_name, new_name) in renames:
            count += self.rename_child(old_name, new_name, _validate=False)
        return count
