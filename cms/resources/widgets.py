# Some pre-configured widgets for use with cms.resources
import deform
from cms.filetempstore import MongoFileUploadTempStore

def get_html_widget(**kwargs):
    return deform.widget.RichTextWidget(width='100%', theme='advanced', **kwargs)

# Be sure site includes a css rule for .wide_input { width: 100%; }
def get_wide_text_widget(**kwargs):
    return deform.widget.TextInputWidget(css_class="wide_input", **kwargs)

def get_wide_textarea_widget(**kwargs):
    return deform.widget.TextAreaWidget(css_class="wide_input", **kwargs)

def get_fileupload_widget(request, **kwargs):
    return deform.widget.FileUploadWidget(_get_fileupload_temp_store(request), **kwargs)

def _get_fileupload_temp_store(request):
    if request is None: return None
    if not hasattr(request, '_tmpstore'):
        tmpstore = MongoFileUploadTempStore(request)
        request._tmpstore = tmpstore
    return request._tmpstore
