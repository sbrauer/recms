from deform.widget import Widget
from colander import null
try:
    import json
except ImportError: # PRAGMA: no cover
    import simplejson as json

class DateUSInputWidget(Widget):
    """
    Renders a JQuery UI date picker widget
    (http://jqueryui.com/demos/datepicker/).  Most useful when the
    schema node is a ``colander_types.DateUS`` object.

    **Attributes/Arguments**

    options
        A dictionary of options that's passed to the jquery datepicker.

    template
        The template name used to render the widget.  Default:
        ``dateinput``.

    readonly_template
        The template name used to render the widget in read-only mode.
        Default: ``readonly/textinput``.
    """
    template = 'dateusinput'
    readonly_template = 'readonly/textinput'
    requirements = ( ('jqueryui', None), )
    option_defaults = {'dateFormat': 'mm/dd/yy',
                       'showOn': 'button',
                       'buttonImage': '/static/calendar-icon.gif',
                       'buttonImageOnly': 'true'
                      }
    options = {}

    def _options(self):
        options = self.option_defaults.copy()
        options.update(self.options)
        return options

    def serialize(self, field, cstruct, readonly=False):
        if cstruct in (null, None):
            cstruct = ''
        template = readonly and self.readonly_template or self.template
        return field.renderer(
            template,
            field=field,
            cstruct=cstruct,
            options=json.dumps(self._options()),
        )

    def deserialize(self, field, pstruct):
        if pstruct in ('', null):
            return null
        return pstruct

class DateTimeUSInputWidget(DateUSInputWidget):
    """
    Renders a JQuery UI date picker widget with a JQuery Timepicker add-on
    (http://trentrichardson.com/examples/timepicker/).  Used for
    ``colander_types.DateTimeUS`` schema nodes.

    **Attributes/Arguments**

    options
        A dictionary of options that's passed to the jquery datetimepicker.

    template
        The template name used to render the widget.  Default:
        ``dateinput``.

    readonly_template
        The template name used to render the widget in read-only mode.
        Default: ``readonly/textinput``.
    """
    template = 'datetimeusinput'
    requirements = ( ('jqueryui', None), ('datetimepicker', None), )
    option_defaults = {'dateFormat': 'mm/dd/yy',
                       #'timeFormat': 'hh:mm TT',
                       'timeFormat': 'hh:mm tt',
                       'ampm': True,
                       'separator': ' ',
                       'showOn': 'button',
                       'buttonImage': '/static/calendar-icon.gif',
                       'buttonImageOnly': 'true'
                      }

