import os
from zope.interface import implements
from pyramid.interfaces import ISession
from dbutil import get_mongodb
from bson.objectid import ObjectId
import datetime, dateutil

def manage_accessed(wrapped):
    """ Decorator which causes a cookie to be set when a wrapped
    method is called"""
    def accessed(session, *arg, **kw):
        session.accessed = dateutil.utcnow()
        if not session._dirty:
            session._dirty = True
            def set_cookie_callback(request, response):
                session._set_cookie(response)
                session.request = None # explicitly break cycle for gc
            session.request.add_response_callback(set_cookie_callback)
        return wrapped(session, *arg, **kw)
    accessed.__doc__ = wrapped.__doc__
    return accessed

def MongoCookieSessionFactoryConfig(
    collection_name='sessions',
    timeout=3600,
    cookie_name='session',
    cookie_max_age=None,
    cookie_path='/',
    cookie_domain=None,
    cookie_secure=False,
    cookie_httponly=False,
    cookie_on_exception=True,
    ):
    """
    Configure a :term:`session factory` which will provide sessions stored in MongoDB
    with the ID stored in a cookie.
    Much was stolen from :func:`pyramid.session.UnencryptedCookieSessionFactoryConfig`,
    so refer to that for more details.
    """

    class MongoCookieSessionFactory(dict):
        """ Dictionary-like session object """
        implements(ISession)

        # configuration parameters
        _collection_name = collection_name

        _cookie_name = cookie_name
        _cookie_max_age = cookie_max_age
        _cookie_path = cookie_path
        _cookie_domain = cookie_domain
        _cookie_secure = cookie_secure
        _cookie_httponly = cookie_httponly
        _cookie_on_exception = cookie_on_exception
        _timeout = datetime.timedelta(0, timeout)

        # dirty flag
        _dirty = False

        def __init__(self, request):
            self._id = None
            self.request = request
            self._collection = get_mongodb(request)[self._collection_name]
            now = dateutil.utcnow()

            # Delete old sessions:
            self._collection.remove({'accessed':{'$lt':now-self._timeout}}, safe=True)

            now = dateutil.utcnow()
            created = accessed = now
            value = None
            state = {}
            cookieval = request.cookies.get(self._cookie_name)
            if cookieval is not None:
                value = self._collection.find_one(dict(_id=ObjectId(cookieval)))
                #print "loaded session: cookieval=%s value=%s" % (repr(cookieval), repr(value))

            if value is not None:
                accessed = value['accessed']
                created = value['created']
                state = value['state']
                self._id = ObjectId(cookieval)
                if now - accessed > self._timeout:
                    state = {}

            self.created = created
            self.accessed = accessed
            dict.__init__(self, state)

        # ISession methods
        def changed(self):
            """ This is intentionally a noop; the session is
            serialized on every access, so unnecessary"""
            pass

        def invalidate(self):
            self.clear() # XXX probably needs to unset cookie

        # non-modifying dictionary methods
        get = manage_accessed(dict.get)
        __getitem__ = manage_accessed(dict.__getitem__)
        items = manage_accessed(dict.items)
        iteritems = manage_accessed(dict.iteritems)
        values = manage_accessed(dict.values)
        itervalues = manage_accessed(dict.itervalues)
        keys = manage_accessed(dict.keys)
        iterkeys = manage_accessed(dict.iterkeys)
        __contains__ = manage_accessed(dict.__contains__)
        has_key = manage_accessed(dict.has_key)
        __len__ = manage_accessed(dict.__len__)
        __iter__ = manage_accessed(dict.__iter__)

        # modifying dictionary methods
        clear = manage_accessed(dict.clear)
        update = manage_accessed(dict.update)
        setdefault = manage_accessed(dict.setdefault)
        pop = manage_accessed(dict.pop)
        popitem = manage_accessed(dict.popitem)
        __setitem__ = manage_accessed(dict.__setitem__)
        __delitem__ = manage_accessed(dict.__delitem__)

        # flash API methods
        @manage_accessed
        def flash(self, msg, queue='', allow_duplicate=True):
            storage = self.setdefault('_f_' + queue, [])
            if allow_duplicate or (msg not in storage):
                storage.append(msg)

        @manage_accessed
        def pop_flash(self, queue=''):
            storage = self.pop('_f_' + queue, [])
            return storage

        @manage_accessed
        def peek_flash(self, queue=''):
            storage = self.get('_f_' + queue, [])
            return storage

        # CSRF API methods
        @manage_accessed
        def new_csrf_token(self):
            token = os.urandom(20).encode('hex')
            self['_csrft_'] = token
            return token

        @manage_accessed
        def get_csrf_token(self):
            token = self.get('_csrft_', None)
            if token is None:
                token = self.new_csrf_token()
            return token

        # non-API methods

        def _set_cookie(self, response):
            if not self._cookie_on_exception:
                exception = getattr(self.request, 'exception', None)
                if exception is not None: # don't set a cookie during exceptions
                    return False

            data = {}
            if self._id: data['_id'] = self._id
            data['created'] = self.created
            data['accessed'] = self.accessed
            data['state'] = dict(self)
            _id = self._collection.save(data, safe=True)
            #print "saved session: _id=%s data=%s" % (repr(_id), repr(data))
            if not self._id: self._id = _id

            response.set_cookie(
                self._cookie_name,
                value=str(self._id),
                max_age = self._cookie_max_age,
                path = self._cookie_path,
                domain = self._cookie_domain,
                secure = self._cookie_secure,
                httponly = self._cookie_httponly,
                )
            return True

    return MongoCookieSessionFactory
