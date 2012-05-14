from gridfs import GridFS
from pyramid.response import Response
from gridfs.errors import NoFile
from pyramid.httpexceptions import HTTPNotFound

def get_mongodb(request):
    if not hasattr(request, '_db'):
        settings = request.registry.settings
        db = settings['db_conn'][settings['db_name']]
        request._db = db
    return request._db

def get_collection(request, name):
    return get_mongodb(request)[name]

def get_gridfs(request, collection='fs'):
    attname = '_grid_%s' % collection
    if not hasattr(request, attname):
        db = get_mongodb(request)
        fs = GridFS(db, collection)
        setattr(request, attname, fs)
    return getattr(request, attname)

def encode_keys(d):
    """ Given a dictionary where the keys are unicode strings (such as a pymongo document),
    return a dictionary with the same values and utf-8 encoded key strings.
    """
    result = {}
    for (key, value) in d.items():
        result[key.encode('utf-8')] = value
    return result

def get_es_conn(request):
    return request.registry.settings['es_conn']

def get_es_index_name(request):
    return request.registry.settings['es_name']

def serve_gridfs_file(file):
    response = Response()
    response.content_type = file.content_type
    response.last_modified = file.upload_date
    response.etag = file.md5
    for chunk in file:
        response.body_file.write(chunk)
    file.close()
    response.content_length = file.length
    return response

def serve_gridfs_file_for_id(request, id, collection='fs'):
    gridfs = get_gridfs(request, collection)
    try:
        file = gridfs.get(id)
    except NoFile, e:
        return HTTPNotFound("No file for id=%s" % id)
    return serve_gridfs_file(file)
