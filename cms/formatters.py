import dateutil

def format_bytes(bytes):
    if (bytes > (1024 * 1024 * 1024)):
        return '%.1f GB' % (bytes / 1024.0 / 1024.0 / 1024.0)
    elif (bytes > (1024 * 1024)):
        return '%.1f MB' % (bytes / 1024.0 / 1024.0)
    elif (bytes > (1024)):
        return '%.1f KB' % (bytes / 1024.0)
    else:
        return '%d bytes' % bytes

# Note: Generally you should use format_localized_datetime() instead,
# since all the datetimes we store in MongoDB are UTC.
def format_datetime(dt, format='%x %X %Z', missing=''):
    if dt:
        return dt.strftime(format).strip()
    else:
        return missing

def format_date(d, format='%x', missing=''):
    return format_datetime(d, format, missing)

def format_localized_datetime(request, dt, format='%x %X %Z', missing=''):
    if dt:
        return format_datetime(dateutil.convert_from_utc(dt, dateutil.get_timezone_for_request(request)), format, missing)
    else:
        return missing
