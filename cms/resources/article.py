from content import Content
import colander, deform
from cms import colander_types
from cms.dateutil import get_timezone_for_request, today_for_request_tz, utcnow
import widgets

# Example implementation of a common content type.
class Article(Content):

    _object_type = "article"

    def get_class_schema(cls, request=None):
        schema = Content.get_class_schema(request)
        #schema.add(colander.SchemaNode(colander_types.DateUS(), name='dateline', default=today_for_request_tz(request)))
        schema.add(colander.SchemaNode(colander_types.DateTimeUS(get_timezone_for_request(request)), name='dateline', default=utcnow()))
        schema.add(colander.SchemaNode(colander.String(), name='body', widget=widgets.get_html_widget()))
        # Single file upload:
        #schema.add(colander.SchemaNode(deform.FileData(), name='attachment', widget=widgets.get_fileupload_widget(request)))

        # Sequence of file uploads:
        schema.add(colander.SchemaNode(colander.Sequence(), colander.SchemaNode(deform.FileData(), widget=widgets.get_fileupload_widget(request)), name='attachments', missing=[], default=[]))
        schema.add(colander.SchemaNode(colander.Boolean(), name='list_attachments', title="List attachments after body?", default=False, missing=False))

        return schema
    get_class_schema = classmethod(get_class_schema)

    def __getitem__(self, name):
        # # Allow traversal to "attachment":
        # if name == 'attachment':
        #     file = self.get_file_for_attribute(name)
        #     if file: return file
        # raise KeyError

        # Allow traversal to one of the "attachments" by filename:
        file = self.get_file_by_filename("attachments", name)
        if file:
            file.__name__ = name
            file.__parent__ = self
            return file
        raise KeyError
