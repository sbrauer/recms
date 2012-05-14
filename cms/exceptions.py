from pyramid.httpexceptions import HTTPForbidden

class Veto(Exception):
    """ May be raised when an attempt is made to do something that the CMS doesn't allow,
    such as adding an object to a folder with a name that's already in use.
    Higher level code (such as views) may want to catch these Veto exceptions
    and present them to end users in a friendly manner.
    """
    def __init__(self, msg):
        Exception.__init__(self, msg)

class NonOrderedFolderException(Exception):
    """ Raised by some Folder methods when an attempt is made to call some method that depends
    on ordering, but the given folder is unordered.
    """
    def __init__(self):
        Exception.__init__(self, "This folder doesn't support ordering.")

class CSRFMismatch(HTTPForbidden):
    """ May be raised by some view code that tries to avoid CSRF attacks.
    """
    def __init__(self):
        HTTPForbidden.__init__(self, "CSRF attempt suspected.")


