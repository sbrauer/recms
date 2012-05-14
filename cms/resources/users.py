from collection import Collection
from object import Object
import colander, deform
from cms.dateutil import utcnow
from hashlib import sha1
import random
import widgets
import permissions
from pyramid.traversal import find_root
from pyramid_mailer import get_mailer
from pyramid_mailer.message import Message

class User(Object):

    _object_type = "user"
    _name_title = "Username"

    def get_class_schema(cls, request=None):
        schema = colander.SchemaNode(colander.Mapping())
        schema.add(colander.SchemaNode(colander.String(), name='firstname', title='First name', widget=widgets.get_wide_text_widget()))
        schema.add(colander.SchemaNode(colander.String(), name='lastname', title='Last name', widget=widgets.get_wide_text_widget()))
        schema.add(colander.SchemaNode(colander.String(), name='email', title='E-mail address', validator=colander.Email(), widget=widgets.get_wide_text_widget()))
        schema.add(colander.SchemaNode(deform.Set(allow_empty=True), name='groups', title='Groups', widget=deform.widget.CheckboxChoiceWidget(values=get_groups_vocabulary(request))))
        schema.add(colander.SchemaNode(colander.Boolean(), name='active', title='Active account', description="A user must be active in able to log in.  You can mark an account as inactive as an alternative to deleting the account.", default=True))
        return schema
    get_class_schema = classmethod(get_class_schema)

    def _get_nonschema_mongo_save_document(self):
        doc = Object._get_nonschema_mongo_save_document(self)
        doc['encoded_password'] = self.encoded_password
        doc['last_logged_in'] = self.last_logged_in
        doc['sortable_fullname'] = self.sortable_fullname.lower()  # a convenient single sort field for the user management page
        return doc

    def _load_nonschema_attributes(self, **kwargs):
        Object._load_nonschema_attributes(self, **kwargs)
        self.encoded_password = kwargs.get('encoded_password', '')
        self.last_logged_in = kwargs.get('last_logged_in', None)

    def set_password(self, password):
        self.encoded_password = self.encode_password(password)

    def set_last_logged_in(self, timestamp=None):
        if not timestamp: timestamp = utcnow()
        self.last_logged_in = timestamp

    def encode_password(self, password, salt=None):
        if salt is None: salt = "%08x" % random.randint(0, 0xffffffff)
        return salt + sha1(password).hexdigest()

    def check_password(self, password):
        if not self.active: return False
        if not self.encoded_password: return False # Don't allow login if no password set.
        salt = self.encoded_password[:-40]
        return self.encoded_password == self.encode_password(password, salt)

    def mail_password(self, password):
        #print "mail password: username=%s password=%s" % (self.__name__, password)
        root = self.find_root()
        # FIXME: make this stuff configurable...
        subject = "Your login info for %s" % root.title
        data = dict(
            site_title = root.title,
            login_url = self.request.resource_url(root, 'login'),
            username = self.__name__,
            password = password,
            remove_addr = self.request.environ['REMOTE_ADDR'],
        )
        body = """Here's the information you'll need to log into %(site_title)s.

The login url is: %(login_url)s

Your username: %(username)s
Your password: %(password)s

Thanks, and have a nice day!

ps. This request was made from %(remove_addr)s.
""" % data
        mailer = get_mailer(self.request)
        message = Message(subject=subject,
                          sender=self.email,
                          recipients=[self.email],
                          body=body)
        mailer.send_immediately(message, fail_silently=False)

    def get_fullname(self):
        return "%s %s" % (self.firstname, self.lastname)

    def get_sortable_fullname(self):
        return "%s, %s" % (self.lastname, self.firstname)

    def __getattr__(self, name):
        if name == 'title':
            return self.get_fullname()
        elif name == 'sortable_fullname':
            return self.get_sortable_fullname()
        raise AttributeError

    def get_groups(self):
        groups = []
        groups_collection = self.find_root()['groups']
        for name in self.groups:
            group = groups_collection.get_child(name)
            if group:
                groups.append(group)
        return groups

class UserCollection(Collection):

    _object_type = "user collection"

    def __init__(self, request):
        self.request = request
        self._collection_name = "users"
        self._child_class = User
        self.title = "Users"
        self.__acl__ = permissions.superuser_only_acl

    def _remove_group_name(self, name):
        self._get_collection().update({'groups':name}, {"$pull":{"groups":name}}, multi=True)

    def get_user_by_email(self, email):
        # There may be more than one user with the same e-mail address... just return the first.
        users = self.get_children(dict(email=email))
        if users: return users[0]
        return None


class Group(Object):
    _object_type = "group"
    # At the moment, Group objects have an empty schema.  Essentially just a name.

    def __getattr__(self, name):
        if name == 'title':
            return self.__name__
        raise AttributeError

    def get_users(self):
        users = self.find_root()['users']
        return users.get_children(spec=dict(groups=self.__name__), sort=[('lastname', 1), ('firstname', 1)])

    def is_system_group(self):
        return self.__name__ in self.__parent__.get_system_group_names()

    def _pre_delete(self):
        Object._pre_delete(self)
        root = self.find_root()
        # Remove group name from User.groups
        root['users']._remove_group_name(self.__name__)
        # Remove group name from Content._local_roles
        root._remove_local_roles_for_principal('group:'+self.__name__)

    def get_content_with_local_roles(self):
        return self.find_root()._get_content_with_local_roles_for_principal('group:'+self.__name__)

class GroupCollection(Collection):

    _object_type = "group collection"

    _system_groups = ('superuser', 'publisher', 'submitter')

    def __init__(self, request):
        self.request = request
        self._collection_name = "groups"
        self._child_class = Group
        self.title = "Groups"
        self.__acl__ = permissions.superuser_only_acl

    def get_system_group_names(self):
        return self._system_groups

    def get_custom_group_names(self):
        return self.get_child_names(sort=[('__name__', 1)])

    def get_group_names(self):
        names = list(self._system_groups)
        for name in self.get_custom_group_names():
            names.append(name)
        return names

    def has_child(self, name):
        if name in self._system_groups: return True
        return Collection.has_child(self, name)

    def get_child(self, name):
        if name in self._system_groups:
            obj = Group(self.request)
            obj.__name__ = name
            obj.__parent__ = self
            return obj
        return Collection.get_child(self, name)

def get_groups_vocabulary(request):
    if request:
        groups = GroupCollection(request)
        return [(x,x) for x in groups.get_group_names()]
    else:
        return []

def generate_random_password(length=8):
    #pool = string.letters + string.digits + string.punctuation
    # The following string avoids confusion between 1l|I and O0. 
    pool = 'abcdefghijkmnopqrstuvwxyz23456789!#$%&*+-/:;=?@'
    chars = []
    while len(chars) < length:
        chars.append(random.choice(pool))
    return ''.join(chars)

# For authtktauthenticationpolicy callback
def groupfinder(username, request):
    root = request.root
    #root = find_root(request.context)
    user = root.get_user(username)
    if user: return ['group:'+x for x in user.groups]
    return []
