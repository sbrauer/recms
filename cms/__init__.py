from pyramid.config import Configurator
from pyramid.settings import asbool, aslist
from cms.resources import root_factory, Content, Root
import pymongo
import pyes
from session import MongoCookieSessionFactoryConfig
from authorization import ACLAuthorizationPolicyWithLocalRoles
from pyramid.events import subscriber, NewRequest

def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    # Handle custom settings that require type conversion.
    db_uri = aslist(settings['db_uri'])
    settings['db_uri'] = db_uri
    es_uri = aslist(settings['es_uri'])
    settings['es_uri'] = es_uri
    es_timeout = float(settings.get('es_timeout', '5.0'))
    settings['es_timeout'] = es_timeout
    filter_unauth_traversal = asbool(settings.get('filter_unauth_traversal'))
    settings['filter_unauth_traversal'] = filter_unauth_traversal

    # Configure this Pyramid app.
    config = Configurator(root_factory=root_factory, settings=settings, session_factory=MongoCookieSessionFactoryConfig(), authorization_policy=ACLAuthorizationPolicyWithLocalRoles())
    zcml_file = settings.get('configure_zcml', 'configure.zcml')
    config.include('pyramid_zcml')
    config.load_zcml(zcml_file)
    config.include('pyramid_mailer')

    # Do initialization based on custom settings.
    db_conn = pymongo.Connection(db_uri, tz_aware=True)
    config.registry.settings['db_conn'] = db_conn
    ensure_db_indexes(db_conn, settings['db_name'])

    es_conn = pyes.ES(es_uri, timeout=es_timeout)
    config.registry.settings['es_conn'] = es_conn
    ensure_es_index(es_conn, settings['es_name'])

    if filter_unauth_traversal:
        config.add_subscriber(filter_unauth_traversal_newrequest_callback, NewRequest)

    # Finally, return a wsgi app.
    return config.make_wsgi_app()

def ensure_db_indexes(conn, db_name):
    db = conn[db_name]
    db['content'].ensure_index([('__parent__', pymongo.ASCENDING), ('__name__', pymongo.ASCENDING)], unique=True)
    #db['history'].ensure_index([('ids', pymongo.ASCENDING), ('time', pymongo.DESCENDING)])
    #db['history'].ensure_index([('user', pymongo.ASCENDING), ('time', pymongo.DESCENDING)])
    db['history'].ensure_index([('ids', pymongo.ASCENDING)])
    db['history'].ensure_index([('user', pymongo.ASCENDING)])
    db['users'].ensure_index([('__name__', pymongo.ASCENDING)], unique=True)
    db['groups'].ensure_index([('__name__', pymongo.ASCENDING)], unique=True)
    # FIXME: add session indexes?
    # FIXME: add indexes to gridfs?

def ensure_es_index(conn, es_name):
    conn.create_index_if_missing(es_name)
    # FIXME: should we have one doctype for all Content, or should each Content subclass have its own doctype/mapping?
    #conn.put_mapping(Content._get_es_doctype(), {'properties':Content._get_es_mapping()}, [es_name])

    for cls in Root._content_type_factories.values():
        conn.put_mapping(cls._get_es_doctype(), {'properties':cls._get_es_mapping()}, [es_name])
    
def filter_unauth_traversal_newrequest_callback(event):
    # cms.resources.Folder.__getitem__ checks for this custom request attribute.
    event.request._filter_unauth_traversal = True

