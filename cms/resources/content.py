from object import Object
import colander, deform
from cms import dbutil
from bson.objectid import ObjectId
from cms.htmlutil import html_to_text
import widgets
import permissions
import repoze.workflow
import zope.interface
from pyramid import security
from interfaces import IContent, ITrash
import pyes

import logging
log = logging.getLogger(__name__)

class Content(Object):
    """ Base type for CMS content objects.
    Content is location-aware (uses the __parent__ attribute).
    Content is indexed in ElasticSearch.
    Content is workflowed with the "publication" workflow.
    """
    zope.interface.implements(IContent)

    _object_type = "content"

    def get_class_schema(cls, request=None):
        """ Return basic schema (title and description) for all Content.
        """
        schema = colander.SchemaNode(colander.Mapping())
        schema.add(colander.SchemaNode(colander.String(), name='title', include_in_other_text=False, widget=widgets.get_wide_text_widget()))

        schema.add(colander.SchemaNode(colander.String(), name='description', include_in_other_text=False, widget=widgets.get_wide_textarea_widget(rows=5)))
        return schema
    get_class_schema = classmethod(get_class_schema)

    def _get_nonschema_mongo_save_document(self):
        doc = Object._get_nonschema_mongo_save_document(self)
        doc['_object_type'] = self._object_type
        doc['__parent__'] = self.__parent__ and self.__parent__._id
        _pub_state = self.get_pub_state()
        if _pub_state: doc['_pub_state'] = _pub_state
        doc['_view'] = self._get_view_principals()
        doc['sortable_title'] = self.sortable_title.lower()
        doc['_in_trash'] = self.in_trash()
        return doc

    def _load_nonschema_attributes(self, **kwargs):
        Object._load_nonschema_attributes(self, **kwargs)
        _pub_state = kwargs.get('_pub_state')
        if _pub_state: self._pub_state = _pub_state

    def _get_view_principals(self):
        return list(security.principals_allowed_by_permission(self, permissions.VIEW))

    def _get_es_doctype(cls):
        #return "content"
        return cls._object_type
    _get_es_doctype = classmethod(_get_es_doctype)

    #
    # If you have the need to index additional attributes of a specific type,
    # override both _get_es_mapping() and _get_es_document() 
    # to call the base methods, get the returned dictionary, and add extra fields
    # to it before returning it.
    #
    # Note that for most types, this won't be necessary since colander.String schema
    # nodes will be added to the "other_text" index automatically (unless you explicitly
    # disable that behavior by setting include_in_other_text=False on the schema node).
    # 
    # If you have string fields that you want to use as categories, tags, or some other 
    # sort of value that you can filter on, be sure to:
    # 1. set include_in_other_text=False on the schema node
    # 2. set index="not_analyzed" in the mapping to disable tokenizing and allow the field 
    #    to be used for sorting
    # 

    def _get_es_mapping(cls):
        mapping = {}
        mapping['__name__'] = dict(type='string', include_in_all=False, index='not_analyzed')
        mapping['_view'] = dict(type='string', include_in_all=False, index='not_analyzed')
        mapping['_pub_state'] = dict(type='string', include_in_all=False, index='not_analyzed')
        mapping['_id_path'] = dict(type='string', include_in_all=False, index='not_analyzed')
        mapping['_object_type'] = dict(type='string', include_in_all=False, index='not_analyzed')
        mapping['title'] = dict(type='string', include_in_all=True, boost=4.0)
        mapping['sortable_title'] = dict(type='string', include_in_all=False, index='not_analyzed')
        mapping['description'] = dict(type='string', include_in_all=True, boost=2.0)
        mapping['other_text'] = dict(type='string', include_in_all=True)
        mapping['_created'] = dict(type='date', format='dateOptionalTime', include_in_all=False)
        mapping['_modified'] = dict(type='date', format='dateOptionalTime', include_in_all=False)
        return mapping
    _get_es_mapping = classmethod(_get_es_mapping)

    def _get_es_document(self):
        doc = dict(__name__ = self.__name__,
                   _object_type = self._object_type,
                   title = self.title,
                   sortable_title = self.sortable_title.lower(),
                   description = self.description,
                   _created = self._created,
                   _modified = self._modified,
                   _id_path = [str(x) for x in self.get_id_path()],
                  )
        doc['_view'] = self._get_view_principals()
        _pub_state = self.get_pub_state()
        if _pub_state: doc['_pub_state'] = _pub_state
        doc['other_text'] = self.get_es_other_text()
        return doc

    def index(self):
        dbutil.get_es_conn(self.request).index(self._get_es_document(), dbutil.get_es_index_name(self.request), self._get_es_doctype(), str(self._id))

    def unindex(self):
        try:
            dbutil.get_es_conn(self.request).delete(dbutil.get_es_index_name(self.request), self._get_es_doctype(), str(self._id))
        except pyes.exceptions.NotFoundException, e:
            pass

    def get_es_other_text(self):
        return '\n'.join(self._get_text_values_for_schema_node(self.get_schema(), self.get_schema_values()))

    def _get_text_values_for_schema_node(self, node, value):
        result = []
        if not value: return result
        if type(node.typ) == colander.Mapping:
            for cnode in node.children:
                name = cnode.name
                val = value.get(name, None)
                if val:
                    result += self._get_text_values_for_schema_node(cnode, val)
        elif type(node.typ) == colander.Sequence:
            if node.children:
                cnode = node.children[0]
                for val in value:
                    result += self._get_text_values_for_schema_node(cnode, val)
        elif type(node.typ) == colander.String:
            if getattr(node, 'include_in_other_text', True):
                if type(node.widget) == deform.widget.RichTextWidget:
                    value = html_to_text(value, 0)
                if value: result.append(value)
        elif type(node.typ) == deform.FileData:
            pass # FIXME: handle PDF, Word, etc
        return result

    def save(self, set_modified=True, index=True):
        # Set pull_parent_from_old_files=False since we want to keep old
        # files around for the edit history log.
        Object.save(self, set_modified=set_modified, pull_parent_from_old_files=False)
        if index: self.index()

    def get_id_path(self):
        ids = []
        obj = self
        while obj:
            parent = obj.__parent__
            if parent: ids.insert(0, parent._id)
            obj = parent
        ids.append(self._id)
        return ids

    def _pre_delete(self):
        self.unindex()
        Object._pre_delete(self)

    def get_sortable_title(self):
        # move articles to the end of the string
        # Example: "The Sound and the Fury" -> "Sound and the Fury, The"
        result = getattr(self, 'title', '')
        lower_title = result.lower()
        for article in ('the', 'a', 'an'):
            if lower_title.startswith(article + ' '):
                result = '%s, %s' % (result[len(article)+1:], result[:len(article)])
        return result

    def get_pub_state(self):
        """ Return this object's state in the publication workflow.
        """
        workflow = get_publication_workflow(self)
        if workflow is None:
            return None
        return workflow.state_of(self)

    def get_pub_workflow_transitions(self):
        workflow = get_publication_workflow(self)
        if workflow is None:
            return []
        return workflow.get_transitions(self, self.request)

    def pub_workflow_transition(self, transition):
        workflow = get_publication_workflow(self)
        workflow.transition(self, self.request, transition)
        self.save()

    def in_trash(self):
        return self.find_interface(ITrash) is not None

    def _get_acl(self):
        # If we're in the trash, we shouldn't have any acl (and inherit the trash acl).
        if self.in_trash(): return None
        # Return the acl for our pub state (if any).
        state = self.get_pub_state()
        #log.debug("in _get_acl(); state=%s" % repr(state))
        if state:
            return permissions.acl_by_state.get(state, None)
        return None

    def __getattr__(self, name):
        if name == '__acl__':
            acl = self._get_acl()
            if acl is not None:
                return acl
        elif name == 'sortable_title':
            return self.get_sortable_title()
        raise AttributeError

    def _get_merged_local_roles(self):
        """ Recurse up from self to root looking for local roles.
        Merge the values together to discover all local roles that apply to self.
        (Note that this method will only compute the result once and cache it;
        later calls will return the cached result.)
        Returns a dictionary where each key is a principal name with one or more
        local roles; each value is a set of system-level group principal names.
        """
        if hasattr(self, '_merged_local_roles'):
            return self._merged_local_roles
        lr = {}
        if hasattr(self, 'get_local_roles'):
            lr = self.get_local_roles()
        merged = {}
        if self.__parent__:
            merged.update(self.__parent__._get_merged_local_roles())
            if lr:
                for (principal, sysgroup) in lr.items():
                    local_sysgroups = merged.get(principal, set())
                    local_sysgroups.add(sysgroup)
                    merged[principal] = local_sysgroups
        else:
            merged = lr
        self._merged_local_roles = merged
        return merged

def get_publication_workflow(context):
    return repoze.workflow.get_workflow(context, 'publication', context)

#################################################
# Workflow callbacks
#################################################

def publication_workflow_elector(context):
    # We don't want the workflow to apply to all types.
    return context._object_type not in ('root', )

def publication_workflow_callback(content, info):
    #log.debug("publication_workflow_callback content=%s info=%s" % (repr(content), repr(info)))
    #log.debug("info.transition="+repr(info.transition))
    # Note that workflow callbacks are called just before the state_attr is set.
    # FIXME: send an event that could be subscribed to (for instance, to send emails)
    pass

