import colander, deform
from cms.filetempstore import MongoFileUploadTempStore
from cms import dbutil, dateutil
import datetime
from pyramid.traversal import find_root, find_resource, find_interface, resource_path
from bson.objectid import ObjectId
from gridfs.errors import NoFile
from copy import deepcopy

class Object(object):
    """ Base class for objects that can be stored in MongoDB.
    Includes support for Deform; simply override the get_class_schema()
    class method to return a Colander schema for your class.
    """

    _object_type = "object"
    
    # Subclasses can override this if a different label for the "__name__" 
    # attribute is desired.
    _name_title = "Name"

    # If a request is passed, it gives us access to request.context, the mongo db connection, and the current user (via pyramid.security.authenticated_userid(request)).
    # Could be handy for default values, vocabulary lists, etc.
    def get_class_schema(cls, request=None):
        schema = colander.SchemaNode(colander.Mapping())
        return schema
    get_class_schema = classmethod(get_class_schema)

    # kwargs should be either a pymongo document (when loading an existing
    # object) or a similar dictionary.  It should NOT be an appstruct with filedicts (see set_appstruct())!
    def __init__(self, request, **kwargs):
        self.request = request
        self.update(**kwargs)
        self._load_nonschema_attributes(**kwargs)

    def get_schema(self):
        return self.get_class_schema(self.request)

    def get_schema_names(self):
        return [node.name for node in self.get_schema().children]

    def _load_nonschema_attributes(self, **kwargs):
        self._id = kwargs.get('_id') # mongodb id
        self._created = kwargs.get('_created')
        self._modified = kwargs.get('_modified')
        _memento = kwargs.get('_memento')
        if _memento is not None: self._memento = _memento

    def _get_nonschema_mongo_save_document(self):
        doc = {}
        doc['__name__'] = self.__name__
        if self._id:
            doc['_id'] =  self._id
        doc['_created'] = getattr(self, '_created', None)
        doc['_modified'] = getattr(self, '_modified', None)
        _memento = getattr(self, '_memento', None)
        if _memento is not None: doc['_memento'] = _memento
        return doc

    def update(self, **kwargs):
        # Updates schema elements using kwargs.
        for name in self.get_schema_names():
            if kwargs.has_key(name):
                setattr(self, name, kwargs[name])

    def get_schema_values(self):
        """ Return a dictionary of this object's schema names and values.
        """
        values = {}
        for name in self.get_schema_names():
            if hasattr(self, name):
                values[name] = deepcopy(getattr(self, name))
        return values

    def get_appstruct(self):
        """ Return an appstruct dictionary for use with an edit form.
        The result is like get_schema_values(), except that all GridFS ObjectIds
        have been replaced with filedicts that use a file upload temp store 
        (as deform expects).
        """
        tmpstore = MongoFileUploadTempStore(self.request)
        return _replace_gridfs_ids_with_filedicts(self.get_schema_values(), tmpstore)

    def set_appstruct(self, appstruct):
        """ Update schema values with data from a deform appstruct.
        All filedicts in the appstruct are replaced with GridFS ObjectIds.
        """
        values = _replace_filedicts_with_gridfs_ids(appstruct)
        self.update(**values)

    def _get_collection(self):
        return self.__parent__._get_collection()

    def save(self, set_modified=True, pull_parent_from_old_files=True):
        if set_modified:
            self._modified = dateutil.utcnow()
            if not getattr(self, '_created', None): self._created = self._modified
        doc = self._get_nonschema_mongo_save_document()

        old_file_ids = []
        new_file_ids = []
        gridfs = dbutil.get_gridfs(self.request)
        if self._id:
            doc['_id'] =  self._id
            for item in gridfs._GridFS__files.find({'parents':self._id}, fields=[]):
                old_file_ids.append(item['_id'])

        schema_values = _prep_schema_values_for_save(self.get_schema_values(), gridfs, new_file_ids)
        doc.update(schema_values)

        _id = self._get_collection().save(doc, safe=True)
        if not self._id: self._id = _id

        # Update file parents:
        # FIXME: Reduce to at most 2 updates by using "$in" queries for "_id".

        if pull_parent_from_old_files:
            for id in old_file_ids:
                if id not in new_file_ids:
                    gridfs._GridFS__files.update({'_id':id}, {"$pull":{"parents":self._id}})
        for id in new_file_ids:
            if id not in old_file_ids:
                gridfs._GridFS__files.update({'_id':id}, {"$addToSet":{"parents":self._id}})

    def _pre_delete(self):
        gridfs = dbutil.get_gridfs(self.request)
        gridfs._GridFS__files.update({'parents':self._id}, {"$pull":{"parents":self._id}}, multi=True)

    def find_root(self):
        return find_root(self)

    def find_resource(self, path):
        return find_resource(self, path)

    def find_interface(self, interface):
        return find_interface(self, interface)

    def resource_path(self, *elements):
        return resource_path(self, *elements)

    def get_file_for_attribute(self, name):
        """ Try to return a GridFS file for the ID whose value is stored in this object's
        attribute named "name".  If the attribute value is a list, try to use the first list item as the ID.
        Return None on failure.
        """
        value = getattr(self, name, None)
        if type(value) == list:
            if len(value):
                value = value[0]
        if value:
            gridfs_file = dbutil.get_gridfs(self.request).get(value)
            if gridfs_file:
                return gridfs_file
        return None

    def get_files_for_attribute(self, name):
        """ Try to return a sequence of GridFS files for the IDs whose values are stored
        in this object's attribute named "name".
        May return an empty list.
        """
        result = []
        value = getattr(self, name, None)
        if value:
            for id in value:
                gridfs_file = dbutil.get_gridfs(self.request).get(id)
                if gridfs_file:
                    result.append(gridfs_file)
        return result

    def get_file_by_filename(self, attname, filename):
        """ Try to return a GridFS file with the given "filename".  Potential files
        are identified by a sequence of IDs stored in the attribute "attname".
        Return None on failure.
        """
        value = getattr(self, attname, None)
        if value:
            gridfs = dbutil.get_gridfs(self.request)
            try:
                return gridfs.get_last_version(filename=filename, _id={'$in':value})
            except NoFile:
                pass
        return None

    def localize_datetime_attribute(self, name):
        value = getattr(self, name, None)
        if value:
            return dateutil.convert_from_utc(value, dateutil.get_timezone_for_request(self.request))
        else:
            return None

    def format_localized_datetime_attribute(self, name, format='%x %X %Z', missing=''):
        dt = self.localize_datetime_attribute(name)
        if dt:
            return dt.strftime(format)
        else:
            return missing

    def format_datetime_attribute(self, name, format='%x %X %Z', missing=''):
        value = getattr(self, name, None)
        if value:
            return value.strftime(format).strip()
        else:
            return missing

    def format_date_attribute(self, name, format='%x', missing=''):
        return self.format_datetime_attribute(name, format, missing)

def _replace_gridfs_ids_with_filedicts(appstruct, tmpstore):
    """ Recurse into an appstruct replacing GridFS IDs with filedicts. """
    if type(appstruct) == dict:
        results = {}
        for (key, value) in appstruct.items():
            results[key] = _replace_gridfs_ids_with_filedicts(value, tmpstore)
        return results
    elif type(appstruct) == list:
        return [_replace_gridfs_ids_with_filedicts(item, tmpstore) for item in appstruct]
    else:
        if type(appstruct) == ObjectId:
            if tmpstore.gridfs.exists(appstruct):
                return _filedict_for_existing_file(tmpstore, appstruct)
        return appstruct

def _filedict_for_existing_file(tmpstore, _id):
    fileuploadwidget = deform.widget.FileUploadWidget(tmpstore)
    while True:
        uid = fileuploadwidget.random_id()
        if fileuploadwidget.tmpstore.get(uid) is None: break
    tmpstore[uid] = {'_id':_id}
    return tmpstore[uid]

def _replace_filedicts_with_gridfs_ids(appstruct):
    """ Recurse into an appstruct replacing filedict instances with GridFS IDs. """
    if type(appstruct) == deform.widget.filedict:
        if appstruct.has_key('_id'):
            return appstruct['_id']
        else:
            return appstruct['fp']._id
    elif type(appstruct) == dict:
        results = {}
        for (key, value) in appstruct.items():
            results[key] = _replace_filedicts_with_gridfs_ids(value)
        return results
    elif type(appstruct) == list:
        return [_replace_filedicts_with_gridfs_ids(item) for item in appstruct]
    else:
        return appstruct

# Crawl schema_values and make sure all types are compatible with pymongo,
# while building up a list of current file ids.
# Convert dates to datetimes and sets to lists.
def _prep_schema_values_for_save(node, gridfs, file_ids):
    if type(node) == dict:
        results = {}
        for (key, value) in node.items():
            results[key] = _prep_schema_values_for_save(value, gridfs, file_ids)
        return results
    elif type(node) == list:
        return [_prep_schema_values_for_save(item, gridfs, file_ids) for item in node]
    else:
        if type(node) == ObjectId:
            if (node not in file_ids) and gridfs.exists(node):
                file_ids.append(node)
        # Pymongo can't handle date objects (without time), so coerce all dates to datetimes.
        elif type(node) is datetime.date:
            return datetime.datetime.combine(node, datetime.time())
        # Pymongo can't handle sets, so coerce to lists.
        elif type(node) is set:
            return list(node)
        return node
