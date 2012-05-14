from folder import Folder
from article import Article
import permissions
from pyramid import security

from bson.objectid import ObjectId
import pyes
from cms import dbutil

from users import UserCollection, GroupCollection, User, generate_random_password
from trash import Trash

class Root(Folder):
    
    _object_type = 'root'

    RESERVED_NAMES = Folder.RESERVED_NAMES + ('users', 'groups', 'trash', 'login', 'logout', 'my_password')

    # Map Content _object_type strings to their classes.
    # This should contain all types that a CMS user could possibly create.
    _content_type_factories = {
        'folder': Folder,
        'article': Article,
    }

    def __init__(self, request, **kwargs):
        Folder.__init__(self, request, **kwargs)
        self.__name__ = ''
        self.__parent__ = None
        self.__acl__ = permissions.root_acl

    def index(self):
        # Don't index the root.
        pass

    def get_content_factory(self, object_type):
        return self._content_type_factories.get(object_type)

    def get_content_by_id(self, _id):
        if _id == 'trash':
            return self['trash']
        if _id == self._id:
            return self
        doc = self._get_collection().find_one({'_id': _id})
        if doc is None:
            return None
        obj = self._construct_child_from_mongo_document(doc)
        pid = doc['__parent__']
        if pid == self._id:
            obj.__parent__ = self
        else:
            parent = self.get_content_by_id(pid)
            if parent:
                obj.__parent__ = parent
                if pid == 'trash':
                    obj.__name__ = str(obj._id)
            else:
                # Parent must have been deleted between call to this method and now.
                return None
        return obj

    # FIXME: add more options to allow searching a specific doctype with extra type-specific filters?
    def search_raw(self, fulltext=None, title=None, description=None, __name__=None, _object_type=None, _pub_state=None, path_id=None, start=0, size=10, fields=None, highlight_fields=None, viewable_only=False, default_operator='AND', sort=None):
        """
        fulltext, title and description should be query strings and may contain
        boolean operators and wildcards

        __name__, _object_type and _pub_state should be either a string or sequence of strings (with OR logic implied) and must be exact matches (no wildcards)

        path_id should be either an ObjectId or a sequence of ObjectIds
        identifying one or more portions of the site to restrict the search to

        sort should be a pyes-style sort string, in other words a comma-delimited list of field names each with the options suffix ":asc" or ":desc"
        (example: "_object_type,_created:desc")

        Returns a pyes result dictionary.
        Keys are [u'hits', u'_shards', u'took', u'timed_out'].
        result['hits'] has the keys: [u'hits', u'total', u'max_score']
        
        result['took'] -> search time in ms
        result['hits']['total'] -> total number of hits
        result['hits']['hits'] -> list of hit dictionaries, each with the keys: [u'_score', u'_type', u'_id', u'_source', u'_index', u'highlight']
        Although if the fields argument is a list of field names (instead 
        of the default value None), instead of a '_source' key, each hit will
        have a '_fields' key whose value is a dictionary of the requested fields.
        
        The "highlight" key will only be present if highlight_fields were used
        and there was a match in at least one of those fields.
        In that case, the value of "highlight" will be dictionary of strings.
        Each dictionary key is a field name and each string is an HTML fragment
        where the matched term is in an <em> tag.
        """
        # Convert singleton values to lists
        if __name__ and (type(__name__) in (str, unicode)):
            __name__ = [__name__]
        if _object_type and (type(_object_type) in (str, unicode)):
            _object_type = [_object_type]
        if _pub_state and (type(_pub_state) in (str, unicode)):
            _pub_state = [_pub_state]
        if type(path_id) == ObjectId:
            path_id = [path_id]

        query = pyes.MatchAllQuery()
        if fulltext or title or description:
            query = pyes.BoolQuery()
            if fulltext: query.add_must(pyes.StringQuery(fulltext, default_operator=default_operator))
            if title: query.add_must(pyes.StringQuery(title, search_fields=['title'], default_operator=default_operator))
            if description: query.add_must(pyes.StringQuery(description, search_fields=['description'], default_operator=default_operator))

        filters = []

        if __name__:
            filters.append(pyes.TermsFilter('__name__', __name__))
        if _object_type:
            filters.append(pyes.TermsFilter('_object_type', _object_type))
        if _pub_state:
            filters.append(pyes.TermsFilter('_pub_state', _pub_state))
        if path_id:
            # Convert ObjectIds to strings
            filters.append(pyes.TermsFilter('_id_path', [str(x) for x in path_id]))
        if viewable_only:
            filters.append(pyes.TermsFilter('_view', security.effective_principals(self.request)))

        if filters:
            query = pyes.FilteredQuery(query, pyes.ANDFilter(filters))

        search = pyes.Search(query=query, start=start, size=size, fields=fields)
        if highlight_fields:
            for field in highlight_fields:
                search.add_highlight(field)
        return dbutil.get_es_conn(self.request).search(search, dbutil.get_es_index_name(self.request), sort=sort or '_score')

    def search(self, fulltext=None, title=None, description=None, __name__=None, _object_type=None, _pub_state=None, path_id=None, start=0, size=10, highlight_fields=None, viewable_only=False, default_operator='AND', sort=None):
        # Return a dictionary with the keys:
        # "total": total number of matching hits
        # "took": search time in ms
        # "items": a list of child objects and highlights for the specified batch of hits

        # We just need the _id values (not _source, etc), so set fields=[]
        result = self.search_raw(fulltext=fulltext, title=title, description=description, __name__=__name__, _object_type=_object_type, _pub_state=_pub_state, path_id=path_id, start=start, size=size, fields=[], highlight_fields=highlight_fields, viewable_only=viewable_only, default_operator='AND', sort=sort)
        items = []
        for hit in result['hits']['hits']:
            _id = ObjectId(hit['_id'])
            obj = self.get_content_by_id(_id)
            if obj:
                items.append(dict(object=obj, highlight=hit.get('highlight')))
        return dict(
            items = items,
            total = result['hits']['total'],
            took = result['took'],
        )

    def __getitem__(self, name):
        if name == 'users':
            users = UserCollection(self.request)
            users.__name__ = 'users'
            users.__parent__ = self
            return users
        elif name == 'groups':
            groups = GroupCollection(self.request)
            groups.__name__ = 'groups'
            groups.__parent__ = self
            return groups
        elif name == 'trash':
            trash = Trash(self.request)
            trash.__name__ = 'trash'
            trash.__parent__ = self
            return trash
        return Folder.__getitem__(self, name)

    def get_user(self, username):
        return self['users'].get_child(username)

    def get_current_user(self):
        return self['users'].get_child(security.authenticated_userid(self.request))

    def get_user_by_email(self, email):
        return self['users'].get_user_by_email(email)

    def add_super_user(self, name='admin', password=None):
        """ Add a new user in the superuser group.
        This is particularly handy to bootstrap a new system in pshell.
        """
        user= User(self.request, firstname=name.capitalize(), lastname='User', groups=['superuser'], active=True, email='')
        if not password:
            password = generate_random_password()
        user.set_password(password)
        self['users'].add_child(name, user)
        print "Created superuser with username %s and password %s" % (name, password)

    # Not for use by "civilians"...

    def _find_local_roles_for_principal(self, principal):
        return self._get_collection().find({'_local_roles.%s' % principal: {"$exists":1}}, fields=['_local_roles'])

    def _get_content_with_local_roles_for_principal(self, principal):
        result = []
        for item in self._find_local_roles_for_principal(principal):
            obj = self.get_content_by_id(item['_id'])
            if obj: result.append(obj)
        return result

    def _remove_local_roles_for_principal(self, principal):
        self._get_collection().update({'_local_roles.%s' % principal: {"$exists": 1}}, {'$unset': {'_local_roles.%s' % principal: 1}}, multi=True)

