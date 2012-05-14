import colander
import datetime
import pytz
import translationstring
from dateutil import convert_datetime

class DateTimeUS(colander.SchemaType):
    """ A type representing a Python ``datetime.datetime`` object.

    This type serializes python ``datetime.datetime`` objects to a
    format commonly used in the United States ("MM/DD/YYYY hh:mm AM"
    or as a strftime format string "%m/%d/%Y %I:%M %p").

    The constructor accepts an argument named ``timezone``
    which can be specified to convert application UTC datetimes
    to local time for display to the user, and to convert user-entered
    local times to UTC datetimes.

    You can adjust the error message reported by this class by
    changing its ``err_template`` attribute in a subclass on an
    instance of this class.  By default, the ``err_template``
    attribute is the string ``Invalid date``.  This string is used as
    the interpolation subject of a dictionary composed of ``val`` and
    ``err``.  ``val`` and ``err`` are the unvalidatable value and the
    exception caused trying to convert the value, respectively. These
    may be used in an overridden err_template as ``${val}`` and
    ``${err}`` respectively as necessary, e.g. ``_('${val} cannot be
    parsed as a date: ${err}')``.

    For convenience, this type is also willing to coerce
    ``datetime.date`` objects to a DateTime string representation
    during serialization.  It does so by using midnight of the day as
    the time.

    Likewise, for convenience, during deserialization, this type will
    convert ``MM/DD/YYYY`` values to a datetime object.  It
    does so by using midnight of the day as the time.

    If the :attr:`colander.null` value is passed to the serialize
    method of this class, the :attr:`colander.null` value will be
    returned.

    The subnodes of the :class:`colander.SchemaNode` that wraps
    this type are ignored.
    """
    err_template =  colander._('Invalid date')

    def __init__(self, timezone='UTC'):
        self.timezone = timezone

    def serialize(self, node, appstruct):
        if appstruct is colander.null:
            return colander.null

        if type(appstruct) is datetime.date: # can't use isinstance; dt subs date
            appstruct = datetime.datetime.combine(appstruct, datetime.time())

        if not isinstance(appstruct, datetime.datetime):
            raise Invalid(node,
                          colander._('"${val}" is not a datetime object',
                            mapping={'val':appstruct})
                          )

        appstruct = convert_datetime(appstruct, pytz.utc, self.timezone)
        #return appstruct.strftime("%m/%d/%Y %I:%M %p")
        return appstruct.strftime("%m/%d/%Y %I:%M %p").lower()

    def deserialize(self, node, cstruct):
        if not cstruct:
            return colander.null

        result = None
        last_e = None

        for format in (
            "%m/%d/%Y %I:%M %p", # full format
            "%m/%d/%Y",          # just the date
        ):
            try:
                result = datetime.datetime.strptime(cstruct, format)
                break
            except ValueError, e:
                last_e = e
                result = None

        if result: return convert_datetime(result, self.timezone, pytz.utc)
        raise colander.Invalid(node, colander._(self.err_template, mapping={'val':cstruct, 'err':last_e}))


class DateUS(colander.SchemaType):
    """ A type representing a Python ``datetime.date`` object.

    This type serializes python ``datetime.date`` objects to a
    format commonly used in the United States ("MM/DD/YYYY"
    or as a strftime format string "%m/%d/%Y").

    You can adjust the error message reported by this class by
    changing its ``err_template`` attribute in a subclass on an
    instance of this class.  By default, the ``err_template``
    attribute is the string ``Invalid date``.  This string is used as
    the interpolation subject of a dictionary composed of ``val`` and
    ``err``.  ``val`` and ``err`` are the unvalidatable value and the
    exception caused trying to convert the value, respectively. These
    may be used in an overridden err_template as ``${val}`` and
    ``${err}`` respectively as necessary, e.g. ``_('${val} cannot be
    parsed as a date: ${err}')``.

    For convenience, this type is also willing to coerce
    ``datetime.datetime`` objects to a date-only string representation
    during serialization.  It does so by stripping off
    any time information, converting the ``datetime.datetime`` into a
    date before serializing.

    Likewise, for convenience, this type is also willing to coerce string
    representations that contain time info into a ``datetime.date``
    object during deserialization.  It does so by throwing away any
    time information related to the serialized value during
    deserialization.

    If the :attr:`colander.null` value is passed to the serialize
    method of this class, the :attr:`colander.null` value will be
    returned.

    The subnodes of the :class:`colander.SchemaNode` that wraps
    this type are ignored.
    """
    err_template =  colander._('Invalid date')

    def serialize(self, node, appstruct):
        if appstruct is colander.null:
            return colander.null

        if isinstance(appstruct, datetime.datetime):
            appstruct = appstruct.date()

        if not isinstance(appstruct, datetime.date):
            raise Invalid(node,
                          colander._('"${val}" is not a date object',
                            mapping={'val':appstruct})
                          )

        return appstruct.strftime("%m/%d/%Y")

    def deserialize(self, node, cstruct):
        if not cstruct:
            return colander.null

        # If time (presumably separated from date by a space) is present, discard it.
        if ' ' in cstruct:
            date, time = cstruct.split(' ', 1)
        else:
            date = cstruct

        try:
            month, day, year = map(int, date.split('/', 2))
            result = datetime.date(year, month, day)
        except Exception, e:
            raise colander.Invalid(node, colander._(self.err_template, mapping={'val':cstruct, 'err':e}))

        return result

# Register default widgets for these types
from deform_widgets import DateUSInputWidget, DateTimeUSInputWidget
from deform.schema import default_widget_makers
default_widget_makers[DateUS] = DateUSInputWidget
default_widget_makers[DateTimeUS] = DateTimeUSInputWidget
