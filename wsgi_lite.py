__all__ = [
    'lite', 'lighten', 'is_lite', 'mark_lite', 'ResponseWrapper',
    'WSGIViolation',
]
try:
    from functools import update_wrapper
except ImportError:
    update_wrapper = None
    try:
        from peak.util.decorators import rewrap
    except ImportError:
        rewrap = None

try:
    from greenlet import greenlet
except ImportError:
    greenlet = None

use_greenlets = greenlet is not None
    
def mark_lite(app):
    """Mark `app` as supporting WSGI Lite, and return it"""
    app.__wsgi_lite__ = True
    return app

def is_lite(app):
    """Does `app` support both WSGI Lite?"""
    return getattr(app, '__wsgi_lite__', False)

def _iter_greenlet(g=None):
    while g: yield g.switch()

function = type(lambda:None)
def maybe_rewrap(app, wrapper):
    if isinstance(app, function):
        if update_wrapper is not None:
            return update_wrapper(wrapper, app)
        elif rewrap is not None:
            return rewrap(app, wrapper)
    return wrapper

def lite(app):
    """Wrap a WSGI Lite app for possible use in a plain WSGI server"""

    if is_lite(app):
        # Don't wrap something that supports wsgi_lite already
        return app

    def wrapper(environ, start_response=None):
        if start_response is None:
            # Called via lite, - just pass through as-is
            return app(environ) 

        # Support wsgi_lite.add_cleanup() callback
        if 'wsgi_lite.add_cleanup' in environ:
            close = None
        else:
            cleanups = []
            environ['wsgi_lite.add_cleanup'] = cleanups.append
            def close():
                if hasattr(body, 'close'):
                    body.close()
                while cleanups:
                    # XXX how to trap errors and clean up from these?
                    cleanups.pop(0)()
                    
        s, h, b = app(environ)
        start_response(s, h)
        if close:
            body = ResponseWrapper(b, close=close)
        return b

    return mark_lite(maybe_rewrap(app, wrapper))









def lighten(app):
    """Wrap a (maybe) non-lite app so it can be called with WSGI Lite"""
    if is_lite(app):
        # Don't wrap something that supports wsgi_lite already
        return app

    def wrapper(environ, start_response=None):
        if start_response is not None:
            # Called from Standard WSGI; just pass through
            return app(environ, start_response)

        headerinfo = []

        def write(data):
            raise NotImplementedError("Greenlets are disabled or missing")

        def start_response(status, headers, exc_info=None):
            if headerinfo and not exc_info:
                raise WSGIViolation("Headers already set & no exc_info given")
            headerinfo[:] = status, headers
            return write

        add_cleanup = environ['wsgi_lite.add_cleanup']
        result = _with_write_support(app, environ, start_response)
        if not headerinfo:
            for data in result:
                if not data and not headerinfo:
                    continue
                elif not headerinfo:
                    raise WSGIViolation("Data yielded w/o start_response")
                elif data:
                    result = ResponseWrapper(result, data)
                    break
        if hasattr(result, 'close'):
            add_cleanup(result.close)

        headerinfo.append(result)
        return tuple(headerinfo)

    return mark_lite(maybe_rewrap(app, wrapper))

def _with_write_support(app, environ, _start_response):
    if greenlet is None or not use_greenlet:
        return app(environ, _start_response)

    # We use this variable to tell whether write() was called from app()
    result = None

    def wrap():
        # We use this variable to tell whether app() has returned yet
        response = None
        def close():
            if hasattr(response, 'close'):
                response.close()

        def write(data):
            if result is None:
                data = ResponseWrapper(
                    _iter_greenlet(greenlet.getcurrent()), data, close
                )
            elif response is not None:
                raise WSGIViolation(
                    "Applications MUST NOT invoke write() from within their"
                    " return iterable - see PEP 333/3333"
                )
            greenlet.getcurrent().parent.switch(data)

        def start_response(status, headers, *exc):
            _start_response(status, headers, *exc)
            return write

        response = app(environ, start_response)
        if result is None:      # write() was never called; ok to pass through
            return response     
        else:
            for data in response:
                write(data)

    # save in result so write() knows it 
    result = greenlet(wrap).switch()    
    return result

class WSGIViolation(AssertionError):
    """A WSGI protocol violation has occurred"""


class ResponseWrapper:
    """Push-back and close() handler for WSGI body iterators

    This lets you wrap an altered body iterator in such a way that its
    original close() method is called at most once.  You can also prepend
    a single piece of body text, or manually specify an alternative close()
    function.
    """

    def __init__(self, result, first=None, close=None):
        self.first = first
        self.result = result
        if close is not None:
            self._close = close
        elif hasattr(result, 'close'):
            self._close = result.close

    def __iter__(self):
        if self.first is not None:
            yield self.first
            self.first = None
        for data in self.result:
            yield data
        self.close()

    _close = None

    def close(self):
        if self._close is not None:
            self._close()
            del self._close






