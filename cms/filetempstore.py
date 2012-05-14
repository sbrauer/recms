from dbutil import get_gridfs
from gridfs.errors import NoFile
from bson.objectid import ObjectId
from deform.widget import filedict
import datetime, dateutil
import logging
log = logging.getLogger(__name__)

# When files are uploaded, they are stored in the GridFS.
# Each file record is assigned an attribute "parents" whose value
# is a list of ObjectIds.  When a file is first uploaded, its parents
# list is empty.  Only when the parent object is saved will the first
# parent ID be assigned to the file.
# Old files without parents can be considered temporary junk, and be deleted;
# see the purge() method below.
#
# This class handles the storage of files in the GridFS, and
# maintains mappings in a custom request attribute (MAPPING_NAME) of Deform file uids to GridFS object _ids.
# To properly maintain the state of the uid-to-object_id mapping across requests while an edit form is handled:
# 1. After getting the appstruct for the initial edit form, call serialize_file_mapping()
#    and store the result in a hidden form field.
# 2. When the form is POSTed:
#    a. before calling form.validate(), get the serialized value from the hidden field and pass it to update_file_mapping_from_serialized()
#    b. if a deform.ValidationFailure occurs, call serialize_file_mapping() again and set the value for
#       the hidden field in the exception's cstruct dictionary.

class MongoFileUploadTempStore(object):

    MAPPING_NAME = "_tmp_files"

    # FIXME: Should the purge really be done on every instantiation, or would
    # it be better to have a nightly job call purge(delete_cutoff) where delete_cutoff
    # is a timedelta?
    def __init__(self, request, collection='fs', delete_cutoff_days=1):
        self.gridfs = get_gridfs(request, collection)
        self.request = request
        self.delete_cutoff_days = datetime.timedelta(delete_cutoff_days)
        self.purge()

    def purge(self):
        cutoff = dateutil.utcnow() - self.delete_cutoff_days
        old_ids = []
        for item in self.gridfs._GridFS__files.find({'parents':[], 'uploadDate':{'$lt':cutoff}}, fields=[]):
            old_ids.append(item['_id'])
        if old_ids:
            log.debug("purging old files: %s" % repr(old_ids))
        for id in old_ids:
            self.gridfs.delete(id)

    def get(self, name, default=None):
        #log.debug("get(%s, %s)" % (repr(name), repr(default)))
        files_dict = self.get_file_mapping()
        _id = files_dict.get(name)
        if _id:
            try:
                result = self.gridfs.get(_id)
            except NoFile, e:
                return default
            return filedict(
                fp=result,
                mimetype=result.content_type,
                uid=name,
                preview_url=self.preview_url_for_id(_id),
                filename=result.name,
                size=result.length,
                _id=_id,
                parents=result.parents
            )
        return default

    def __setitem__(self, name, value):
        #log.debug("__setitem__(%s, %s)" % (repr(name), repr(value)))
        if value.has_key('_id'):
            _id = value['_id']
        else:
            _id = self.gridfs.put(value['fp'], filename=value['filename'], contentType=value['mimetype'], parents=[])
            value['_id'] = _id
            value['parents'] = []
            value['preview_url'] = self.preview_url_for_id(_id)
        files_dict = self.get_file_mapping()
        files_dict[name] = _id
        setattr(self.request, self.MAPPING_NAME, files_dict)

    def __getitem__(self, name):
        #log.debug("__getitem__(%s)" % repr(name))
        return self.get(name)

    def __contains__(self, name):
        #log.debug("__contains__(%s)" % repr(name))
        files_dict = self.get_file_mapping()
        _id = files_dict.get(name)
        if _id:
            return self.gridfs.exists(_id)
        return False

    def preview_url(self, uid):
        #log.debug("preview_url(%s)" % repr(uid))
        _id = self.get_file_mapping().get(uid)
        return self.preview_url_for_id(_id)

    def preview_url_for_id(self, _id):
        # There should be a view to handle these urls.
        return "%s/serve_file/%s" % (self.request.application_url, str(_id))

    def get_file_mapping(self):
        return getattr(self.request, self.MAPPING_NAME, {})

    def serialize_file_mapping(self):
        items = []
        for (uid, _id) in self.get_file_mapping().items():
            items.append("%s:%s" % (uid, str(_id)))
        return ",".join(items)

    def _deserialize_file_mapping(self, serialized_string):
        """ Deserialize a string such as returned from serialize_file_mapping().
        """
        files_dict = {}
        if serialized_string:
            for item in serialized_string.split(','):
                (uid, _id) = item.split(':', 1)
                files_dict[uid] = ObjectId(_id)
        return files_dict

    def update_file_mapping_from_serialized(self, serialized_string):
        deserialized_dict = self._deserialize_file_mapping(serialized_string)
        files_dict = self.get_file_mapping()
        for (uid, _id) in deserialized_dict.items():
            # If the current mapping has this uid, the user must have uploaded a new file,
            # so skip the uid (otherwise it would revert to the original file).
            if not files_dict.has_key(uid):
                files_dict[uid] = _id
        setattr(self.request, self.MAPPING_NAME, files_dict)
