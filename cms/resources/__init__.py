from object import Object
from collection import Collection
from content import Content
from folder import Folder
from root import Root
from article import Article
from users import User, UserCollection, Group, GroupCollection

from cms import dbutil

def root_factory(request):
    doc = dbutil.get_collection(request, 'content').find_one(dict(_object_type='root'))
    if doc:
        root = Root(request, **(dbutil.encode_keys(doc)))
    else:
        data = dict(
            title="CMS Demo Site",
            description="This site is a demo of a CMS based on Pyramid, MongoDB and ElasticSearch.",
            _is_ordered=True,
        )
        # Run data thru a schema serialize/deserialize to pick up default values for other schema fields.
        schema = Root.get_class_schema(request)
        data = schema.deserialize(schema.serialize(data))
        root = Root(request, **data)
        root.save()
    return root
