from content import Content
from collection import Collection
import colander, deform
from pyramid import security
from cms import orderutil
import widgets
from cms.exceptions import NonOrderedFolderException, Veto

class BaseFolder(Content, Collection):
    """ A Content object that can also behave like a Collection.
    Folders are stored in the "content" collection and can be
    arranged in a hierarchy.
    Each direct child of a Folder must have a unique __name__ in the context
    of that folder.
    """

    _object_type = 'base folder'

    def get_class_schema(cls, request=None):
        schema = Content.get_class_schema(request)
        schema.add(colander.SchemaNode(colander.Boolean(), name='_is_ordered', title="Enable child ordering?", default=False, missing=False, description="Enable this option if you need explicit control over ordering of child objects.  Please avoid enabling this option on folders with a large number of children where sorting is more appropriate."))

        return schema
    get_class_schema = classmethod(get_class_schema)

    # Declare the _object_types that this class allows as children.
    # Subclasses and even instances may wish to override this tuple.
    #_allowed_child_types = ('article', 'folder', )
    _allowed_child_types = ()

    def __init__(self, request, **kwargs):
        Content.__init__(self, request, **kwargs)
        self._collection_name = "content"

    def _get_collection(self):
        return Collection._get_collection(self)

    def _get_child_class(self, doc):
        return self.find_root().get_content_factory(doc['_object_type'])

    def _get_nonschema_mongo_save_document(self):
        doc = Content._get_nonschema_mongo_save_document(self)
        doc['_local_roles'] = self.get_local_roles()
        doc['_ordered_names'] = self.get_ordered_names()
        return doc

    def _load_nonschema_attributes(self, **kwargs):
        Content._load_nonschema_attributes(self, **kwargs)
        _local_roles = kwargs.get('_local_roles')
        if _local_roles: self._local_roles = _local_roles
        _ordered_names = kwargs.get('_ordered_names')
        if _ordered_names is not None: self._ordered_names = _ordered_names

    def _morph_spec(self, spec):
        if spec is None: spec = {}
        # Make sure parent is in the spec.
        spec['__parent__'] = self._id
        return spec

    def _add_view_to_spec(self, spec):
        principals = security.effective_principals(self.request)
        # Don't even bother modifying the spec if the user is in the superuser group.
        if 'group:superuser' in principals: return spec
        if spec is None: spec = {}
        spec['_view'] = {'$in': principals}
        return spec

    def get_viewable_child(self, name):
        spec = self._morph_spec({'__name__': name})
        spec = self._add_view_to_spec(spec)
        doc = self._get_collection().find_one(spec)
        if doc is None:
            return None
        return self._construct_child_from_mongo_document(doc)

    def __getitem__(self, name):
        # If the ".ini" setting "filter_unauth_traversal=true" was used, a NewRequest event handler
        # sets request._filter_unauth_traversal=True.
        # If this request attribute was set and the user is unauthenticated, treat unviewable children
        # as if they don't exist so the user gets a 404 when trying to traverse to them.
        if getattr(self.request, '_filter_unauth_traversal', False) and not security.authenticated_userid(self.request):
            child = self.get_viewable_child(name)
        else:
            child = self.get_child(name)
        if child is None:
            raise KeyError
        return child

    def get_viewable_children_and_total(self, spec=None, sort=None, skip=0, limit=0):
        spec = self._add_view_to_spec(spec)
        return Collection.get_children_and_total(self, spec=spec, sort=sort, skip=skip, limit=limit)

    def get_viewable_children(self, spec=None, sort=None, skip=0, limit=0):
        spec = self._add_view_to_spec(spec)
        return Collection.get_children(self, spec=spec, sort=sort, skip=skip, limit=limit)

    def get_viewable_child_names_and_total(self, spec=None, sort=None, skip=0, limit=0):
        spec = self._add_view_to_spec(spec)
        return Collection.get_child_names_and_total(self, spec=spec, sort=sort, skip=skip, limit=limit)

    def get_viewable_child_names(self, spec=None, sort=None, skip=0, limit=0):
        spec = self._add_view_to_spec(spec)
        return Collection.get_child_names(self, spec=spec, sort=sort, skip=skip, limit=limit)

    def get_viewable_children_lazily(self, spec=None, sort=None):
        spec = self._add_view_to_spec(spec)
        return Collection.get_children_lazily(self, spec=spec, sort=sort)

    def get_ordered_children(self):
        names = self.get_ordered_names()
        if names is None: raise NonOrderedFolderException()
        children = self.get_children()
        return _order_objects_by_names(children, names)

    def get_viewable_ordered_children(self):
        names = self.get_ordered_names()
        if names is None: raise NonOrderedFolderException()
        children = self.get_viewable_children()
        return _order_objects_by_names(children, names)

    def add_child(self, name, child):
        Collection.add_child(self, name, child)
        names = self.get_ordered_names()
        if names is not None:
            names.append(name)
            self._ordered_names = names
            self.save()

    def delete_child(self, name):
        Collection.delete_child(self, name)
        self._child_removed(name)

    def _child_removed(self, name):
        names = self.get_ordered_names()
        if (names is not None) and (name in names):
            names.remove(name)
            self._ordered_names = names
            self.save()

    def rename_child(self, name, newname, _validate=True):
        if Collection.rename_child(self, name, newname, _validate=_validate):
            names = self.get_ordered_names()
            if names is not None:
                idx = names.index(name)
                names[idx] = newname
                self._ordered_names = names
                self.save()
            return 1
        else:
            return 0

    def reorder_names_up(self, names_to_reorder, delta=1):
        names = self.get_ordered_names()
        if names is None: raise NonOrderedFolderException()
        reordered_names = orderutil.reorder_ids_up(names, names_to_reorder, delta)
        if reordered_names:
            self._ordered_names = names
            self.save()
        return reordered_names

    def reorder_names_down(self, names_to_reorder, delta=1):
        names = self.get_ordered_names()
        if names is None: raise NonOrderedFolderException()
        reordered_names = orderutil.reorder_ids_down(names, names_to_reorder, delta)
        if reordered_names:
            self._ordered_names = names
            self.save()
        return reordered_names

    def reorder_names_to_top(self, names_to_reorder):
        names = self.get_ordered_names()
        if names is None: raise NonOrderedFolderException()
        reordered_names = orderutil.reorder_ids_to_top(names, names_to_reorder)
        if reordered_names:
            self._ordered_names = names
            self.save()
        return reordered_names

    def reorder_names_to_bottom(self, names_to_reorder):
        names = self.get_ordered_names()
        if names is None: raise NonOrderedFolderException()
        reordered_names = orderutil.reorder_ids_to_bottom(names, names_to_reorder)
        if reordered_names:
            self._ordered_names = names
            self.save()
        return reordered_names

    def _pre_delete(self):
        # If I'm being deleted, my kids are going down with me.
        for name in self.get_child_names():
            self.delete_child(name)
        Content._pre_delete(self)

    def get_unique_name(self, name, suffix='', sep='-'):
        """ Given a desired name (and optional suffix), try to return a unique name.
        Say name='foo'.  If there's no child named 'foo' already, return 'foo'.
        Otherwise try 'foo-1', then 'foo-2', etc.
        If suffix is passed, it will be added to each name.  For example, if name='foo' and suffix='.jpg',
        we'll try the names "foo.jpg", "foo-1.jpg", "foo-2.jpg", etc.
        """
        attempt = 0
        while 1:
            if attempt:
                candidate = "%s%s%s%s" % (name, sep, attempt, suffix)
            else:
                candidate = name+suffix
            if not self.has_child(candidate):
                return candidate
            attempt += 1

    def veto_add_child(self, name, child, unique=True):
        # Return an error message (string) if there's any reason why the specified child can't be added with the specified name.
        # Otherwise return None
        if child._object_type not in self._allowed_child_types:
            return "This %s does not allow child objects of type %s." % (self._object_type, child._object_type)
        error = Collection.veto_add_child(self, name, child, unique=unique)
        if error: return error
        return None

    def veto_move_child(self, obj):
        if obj._id == self._id:
            return "Can't move an object into itself."
        if obj._id in self.get_id_path():
            return "Can't move an object into a child of itself."
        return self.veto_add_child(obj.__name__, obj)

    def move_child(self, obj):
        """ Move an object into this folder. """
        if obj.__parent__._id == self._id: return 0
        error = self.veto_move_child(obj)
        if error: raise Veto(error)
        orig_parent = obj.__parent__
        self.add_child(obj.__name__, obj)
        index_recursively(obj, include_self=False)
        # Notify old parent that child was moved (gives ordered folders an opportunity to update their ordered name list).
        orig_parent._child_removed(obj.__name__)
        return 1

    def veto_move_children(self, objects):
        """ This method will return an error string if there is a problem with any of the proposed moves.
        Else returns None.
        """
        new_names = set()
        for obj in objects:
            obj_name = obj.__name__
            error = self.veto_move_child(obj)
            if error: return "Cannot move \"%s\". %s" % (obj_name, error)
            if obj_name in new_names:
                return "The name \"%s\" would not be unique." % obj_name
            new_names.add(obj_name)
        return None

    def move_children(self, objects):
        """ Move several objects into this folder.
        This method will return the number of moves successfully preformed.
        This method will validate the proposed moves first and raise an exception if there is any problem.
        """
        error = self.veto_move_children(objects)
        if error: raise Veto(error)
        count = 0
        for obj in objects:
            count += self.move_child(obj)
        return count


    def copy_child(self, obj):
        """ Copy/clone child object into this Folder.
        Use the same __name__ as the original, unless a child with that name already exists.
        In that case, try "NAME-1", "NAME-2", etc.
        Return the copy object.
        """
        root = self.find_root()
        newchild = root.get_content_by_id(obj._id)
        newchild._id = None
        newchild._created = None
        # Clear _pub_state, if any.
        if hasattr(newchild, '_pub_state'):
            del newchild._pub_state
        newname = obj.__name__
        if self.has_child(newname): newname = self.get_unique_name(newname)
        self.add_child(newname, newchild)
        # Recursively copy children...
        if isinstance(obj, Folder):
            for child in obj.get_children_lazily():
                newchild.copy_child(child)
        return newchild
    

    def veto_copy_children(self, objects):
        """ This method will return an error string if there is a problem with any of the proposed copies.
        Else returns None.
        """
        for obj in objects:
            error = self.veto_add_child(obj.__name__, obj, unique=False)
            if error: return "Cannot move \"%s\". %s" % (obj.__name__, error)
        return None

    def copy_children(self, objects):
        """ Copy several objects into this folder.
        This method will return a list of 2-tuples, where each is a pair of (original_object, copy_object).
        This method will validate the proposed copies first and raise an exception if there is any problem.
        """
        error = self.veto_copy_children(objects)
        if error: raise Veto(error)
        result = []
        for obj in objects:
            new_obj = self.copy_child(obj)
            result.append((obj, new_obj))
        return result

    def pub_workflow_transition(self, transition, save_children=True):
        """ Apply a workflow transition to this Folder, and (unless save_children==False)
        we also want to update "_view" fields of all children in both mongo and elastic by
        calling their save() method.
        """
        Content.pub_workflow_transition(self, transition)
        if save_children:
            save_recursively(self, include_self=False, set_modified=False)

    def pub_workflow_transition_recursively(self, transition, include_self=True):
        """ Apply a workflow transition to this Folder (unless include_self==False)
        and recurse into children trying to apply the same transition if it applies.
        Returns a set of ObjectIds for the objects that were transitioned.
        """
        result = set()
        if include_self:
            self.pub_workflow_transition(transition, save_children=False)
            result.add(self._id)
        for child in self.get_children_lazily():
            transition_applies = transition in [x['name'] for x in child.get_pub_workflow_transitions()]
            is_folder = isinstance(child, Folder)
            if transition_applies:
                if is_folder:
                    result.update(child.pub_workflow_transition_recursively(transition))
                else:
                    child.pub_workflow_transition(transition)
                    result.add(child._id)
            else:
                # We want the child's "_view" field to be updated in both mongo and elastic.
                child.save(set_modified=False)
                if is_folder:
                    result.update(child.pub_workflow_transition_recursively(transition, include_self=False))
        return result

    def get_local_roles(self):
        return getattr(self, '_local_roles', {})

    def is_ordered(self):
        return getattr(self, '_is_ordered', False)

    def get_ordered_names(self):
        if self.is_ordered():
            if not hasattr(self, '_ordered_names'):
                # This folder must have just had ordering enabled.  Initialize the ordered list.
                self._ordered_names = self.get_child_names()
            return getattr(self, '_ordered_names')
        else:
            return None

    def set_local_roles(self, local_roles):
        """ local_roles should be a dictionary where the keys are principal names and the values are system-level group names.
        For example, if you want the group "news" to have the same access as the system-level "publisher" group in this folder,
        you would set local_roles to {'group:news': 'group:publisher'}
        """
        self._local_roles = local_roles
        self.save(set_modified=False)
        # FIXME: A recursive save is only necessary if view permission is only allowed to certain authenticated users/groups.
        # Consider adding an ".ini" setting for sites that require such strict access control of the view perm.
        #save_recursively(self, include_self=False, set_modified=False)

# Some utility functions...

def recurse_content(obj, include_self=True):
    def visit(node, include_self=True):
        if include_self: yield node
        if isinstance(node, Folder):
            for child in node.get_children_lazily():
                for result in visit(child):
                    yield result
    return visit(obj, include_self)

def index_content(obj):
    if isinstance(obj, Content):
        obj.index()

def unindex_content(obj):
    if isinstance(obj, Content):
        obj.unindex()

def index_recursively(obj, include_self=True):
    for node in recurse_content(obj, include_self=include_self):
        index_content(node)

def unindex_recursively(obj, include_self=True):
    for node in recurse_content(obj, include_self=include_self):
        unindex_content(node)

def save_recursively(obj, include_self=True, set_modified=True, index=True):
    for node in recurse_content(obj, include_self=include_self):
        node.save(set_modified=set_modified, index=index)

def _order_objects_by_names(objects, names):
    objects_by_name = {}
    for obj in objects:
        objects_by_name[obj.__name__] = obj
    result = []
    for name in names:
        obj = objects_by_name.get(name, None)
        if obj: result.append(obj)
    return result

class Folder(BaseFolder):
    """ Extends BaseFolder adding schema attributes that allow a CMS user to customize a folder's default view.
    """

    _object_type = 'folder'

    # Declare the _object_types that this class allows as children.
    # Subclasses and even instances may wish to override this tuple.
    _allowed_child_types = ('article', 'folder', )

    VIEW_STYLE_CHOICES = (
        ('list_children', 'list children'),
        ('display_specific_child', 'display specific child'),
        ('redirect_first_viewable', 'redirect to first viewable child'),
        ('use_template', 'use a template'),
        ('use_view', 'use a view'),
    )

    LIST_ITEM_STYLE_CHOICES = (
        ('title', 'title only'),
        ('title_description', 'title and description'),
        ('title_date', 'title and date'),
        ('title_date_description', 'title, date and description'),
        ('title_description_date', 'title, description and date'),
    )

    DATE_CHOICES = (
        ('_created', 'created'),
        ('_modified', 'modified'),
        ('_other', 'other'),
    )

    SORT_CHOICES = (
        ('', 'none'),
        ('sortable_title', 'title'),
        ('__name__', 'name'),
        ('_created', 'created'),
        ('_modified', 'modified'),
        ('_other', 'other'),
    )

    SORT_DIR_CHOICES = (
        ('asc', 'ascending'),
        ('desc', 'descending'),
    )

    def get_class_schema(cls, request=None):
        schema = BaseFolder.get_class_schema(request)

        sort1_settings = colander.SchemaNode(colander.Mapping(), name='sort1_settings', title='Primary sort')

        sort1_settings.add(colander.SchemaNode(colander.String(), name='field', include_in_other_text=False, title="Primary sort field", default='', missing='', widget=deform.widget.SelectWidget(values=cls.SORT_CHOICES), description="When child ordering is disabled, the field specified here is used as the primary sort key when listing child objects."))
        sort1_settings.add(colander.SchemaNode(colander.String(), name='other', include_in_other_text=False, title="Primary sort field other", widget=widgets.get_wide_text_widget(), default='', missing='', description="The name of another field (when the primary sort field is set to \"other\")."))
        sort1_settings.add(colander.SchemaNode(colander.String(), name='dir', include_in_other_text=False, title="Primary sort direction", default='asc', missing='asc', widget=deform.widget.SelectWidget(values=cls.SORT_DIR_CHOICES)))
        sort1_settings.validator = sort_settings_validator
        schema.add(sort1_settings)

        sort2_settings = colander.SchemaNode(colander.Mapping(), name='sort2_settings', title='Secondary sort')

        sort2_settings.add(colander.SchemaNode(colander.String(), name='field', include_in_other_text=False, title="Secondary sort field", default='', missing='', widget=deform.widget.SelectWidget(values=cls.SORT_CHOICES), description="When child ordering is disabled, the field specified here is used as the secondary sort key when listing child objects."))
        sort2_settings.add(colander.SchemaNode(colander.String(), name='other', include_in_other_text=False, title="Secondary sort field other", widget=widgets.get_wide_text_widget(), default='', missing='', description="The name of another field (when the secondary sort field is set to \"other\")."))
        sort2_settings.add(colander.SchemaNode(colander.String(), name='dir', include_in_other_text=False, title="Secondary sort direction", default='asc', missing='asc', widget=deform.widget.SelectWidget(values=cls.SORT_DIR_CHOICES)))
        sort2_settings.validator = sort_settings_validator
        schema.add(sort2_settings)

        schema.add(colander.SchemaNode(colander.String(), name='view_style', include_in_other_text=False, title="Folder view style", default='list_children', widget=deform.widget.SelectWidget(values=cls.VIEW_STYLE_CHOICES), description="This field determines what will be displayed when a user views this folder.  Depending on the setting you select in this field, some of the other fields below may become required."))
        child_list_settings = colander.SchemaNode(colander.Mapping(), name='child_list_settings', title='Child listing settings')
        child_list_settings.add(colander.SchemaNode(colander.String(), name='list_item_style', include_in_other_text=False, title="List item style", default='title_only', missing='title_only', widget=deform.widget.SelectWidget(values=cls.LIST_ITEM_STYLE_CHOICES), description="This field determines what fields will be displayed for each child item listed."))
        child_list_settings.add(colander.SchemaNode(colander.String(), name='display_date', include_in_other_text=False, title="Date to display", default='_created', missing='_created', widget=deform.widget.SelectWidget(values=cls.DATE_CHOICES), description="This field determines which date will be displayed for each child (when list item style includes date)."))
        child_list_settings.add(colander.SchemaNode(colander.String(), name='other_display_date', include_in_other_text=False, title="Other display date", widget=widgets.get_wide_text_widget(), default='', missing='', description="The name of another date field (when the date to display is set to \"other\")."))
        child_list_settings.add(colander.SchemaNode(colander.String(), name='intro', widget=widgets.get_html_widget(), default='', missing='', description="Any content entered here will be displayed before the list of child objects."))
        child_list_settings.add(colander.SchemaNode(colander.String(), name='outro', widget=widgets.get_html_widget(), default='', missing='', description="Any content entered here will be displayed after the list of child objects."))
        child_list_settings.add(colander.SchemaNode(colander.Boolean(), name='intro_outro_first_page_only', title="Show intro and outro on first page only?", default=False, missing=False, description="For unordered folders, large numbers of children will be split across multiple pages.  In such a case, the intro and outro will be displayed on all pages unless you enable this option."))
        child_list_settings.validator = child_list_settings_validator
        schema.add(child_list_settings)
        schema.add(colander.SchemaNode(colander.String(), name='specific_child_name', include_in_other_text=False, title="Name of child to display", widget=widgets.get_wide_text_widget(), default='index', missing='', description="The name of a specific child to try to display (when the view style is \"display specific child\")."))
        schema.add(colander.SchemaNode(colander.String(), name='template_name', include_in_other_text=False, title="Name of template", widget=widgets.get_wide_text_widget(), default='', missing='', description="The name of a template to render on this folder (when the view style is \"use a template\")."))
        schema.add(colander.SchemaNode(colander.String(), name='view_name', include_in_other_text=False, title="Name of view", widget=widgets.get_wide_text_widget(), default='', missing='', description="The name of a view to render on this folder (when the view style is \"use a view\")."))
        schema.validator = schema_validator
        return schema
    get_class_schema = classmethod(get_class_schema)

    def get_default_sort(self):
        result = []
        for i in (1, 2):
            settings = getattr(self, "sort%s_settings" % i, None)
            if settings:
                field = settings.get('field')
                if field:
                    if field == '_other':
                        field = settings.get('other')
                if field:
                    dir = settings.get('dir', 'asc')
                    if dir == 'desc': dir = -1
                    else: dir = 1
                    result.append((field, dir))
        return result

    def get_sorted_children_and_total(self, spec=None, skip=0, limit=0):
        return Collection.get_children_and_total(self, spec=spec, sort=self.get_default_sort(), skip=skip, limit=limit)

    def get_sorted_children(self, spec=None, skip=0, limit=0):
        return Collection.get_children(self, spec=spec, sort=self.get_default_sort(), skip=skip, limit=limit)

    def get_viewable_sorted_children_and_total(self, spec=None, skip=0, limit=0):
        spec = self._add_view_to_spec(spec)
        return Collection.get_children_and_total(self, spec=spec, sort=self.get_default_sort(), skip=skip, limit=limit)

    def get_viewable_sorted_children(self, spec=None, skip=0, limit=0):
        spec = self._add_view_to_spec(spec)
        return Collection.get_children(self, spec=spec, sort=self.get_default_sort(), skip=skip, limit=limit)

def schema_validator(form, value):
    errors = {}
    view_style = value['view_style']
    if view_style == 'display_specific_child':
        if not value['specific_child_name']:
            errors['specific_child_name'] = 'Required when view style is "display specific child"'
    elif view_style == 'use_template':
        if not value['template_name']:
            errors['template_name'] = 'Required when view style is "use a template"'
    elif view_style == 'use_view':
        if not value['view_name']:
            errors['view_name'] = 'Required when view style is "use a view"'
    if errors:
        exc = colander.Invalid(form)
        for (key, val) in errors.items():
            exc[key] = val
        raise exc

def sort_settings_validator(form, value):
    errors = {}
    if value['field'] == '_other':
        if not value['other']:
            errors['other'] = 'Required when sort field is set to "other".'
    if errors:
        exc = colander.Invalid(form)
        for (key, val) in errors.items():
            exc[key] = val
        raise exc

def child_list_settings_validator(form, value):
    errors = {}
    if value['display_date'] == '_other':
        if not value['other_display_date']:
            errors['other_display_date'] = 'Required when display date is set to "other".'
    if errors:
        exc = colander.Invalid(form)
        for (key, val) in errors.items():
            exc[key] = val
        raise exc
