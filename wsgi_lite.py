__all__ = [
    'lite', 'lighten', 'is_lite', 'mark_lite', 'WSGIViolation',
]

try:
    from greenlet import greenlet
except ImportError: # pragma: no cover
    greenlet = None

use_greenlets = True
    
def mark_lite(app):
    """Mark `app` as supporting WSGI Lite, and return it"""
    app.__wsgi_lite__ = True
    return app

def is_lite(app):
    """Does `app` support both WSGI Lite?"""
    return getattr(app, '__wsgi_lite__', False)

def _iter_greenlet(g=None):
    while g:
        v = g.switch()
        if v is not None:
            yield v

try:
    from new import function
except ImportError:
    from types import FunctionType as function
    
def renamed(f, name):
    return function(
        f.func_code, f.func_globals, name, f.func_defaults, f.func_closure
    )
    
def maybe_rewrap(app, wrapper):
    if isinstance(app, function):
        wrapper = renamed(wrapper, app.func_name)
        wrapper.__module__ = app.__module__
        wrapper.__doc__    = app.__doc__
        wrapper.__dict__.update(app.__dict__)
    return wrapper


def lite(__name_or_func__=None, __doc__=None, __module__=None, **kw):
    """Wrap a WSGI Lite app for possible use in a plain WSGI server"""
    isfunc = isinstance(__name_or_func__, function)

    if isfunc and not kw and __doc__ is None and __module__ is None:
        return _lite(__name_or_func__)
    elif kw and not isfunc:
        return rebinder(_lite, __name_or_func__, __doc__, __module__, **kw)
    else:
        raise TypeError(
            "Usage: @lite or @lite(**kw) or lite(name?, doc?, module?, **kw)"
        )

def _lite(app):
    """Provide a conversion wrapper (if needed) for WSGI 1 -> WSGI Lite"""
    if is_lite(app):
        return app  # Don't wrap something that supports wsgi_lite already

    bindings = {}
    def wrapper(environ, start_response=None):
        # Is it a WSGI 1 call?
        if start_response is not None:   
            close = get_closer(environ)  # Support wsgi_lite.closing() callback
            if bindings:
                s, h, b = with_bindings(bindings, app, environ)
            else:
                s, h, b = app(environ)
            start_response(s, h)
            return wrap_response(b, close=close)

        # Called via lite, so just pass through as-is, w/optional bindings
        else:
            if bindings:
                return with_bindings(bindings, app, environ)       
            else:
                return app(environ)

    wrapper = maybe_rewrap(app, wrapper)
    wrapper.__wl_bind_info__ = app, bindings
    return mark_lite(wrapper)

def lighten(app):
    """Wrap a (maybe) non-lite app so it can be called with WSGI Lite"""
    if is_lite(app):
        # Don't wrap something that supports wsgi_lite already
        return app
    def wrapper(environ, start_response=None):
        if start_response is not None:
            # Called from Standard WSGI - we're just passing through
            close = get_closer(environ)  # enable extension before we go
            return wrap_response(app(environ, start_response), close=close)
        headerinfo = []
        data = None
        def write(data):
            raise NotImplementedError("Greenlets are disabled or missing")
        def start_response(status, headers, exc_info=None):
            if exc_info:
                try:
                    if data: raise exc_info[0], exc_info[1], exc_info[2]
                finally:
                    exc_info = None        # avoid dangling circular ref
            elif headerinfo and data:
                raise WSGIViolation("Headers already sent & no exc_info given")
            headerinfo[:] = status, headers
            return write
        closing = environ['wsgi_lite.closing']
        result = _with_write_support(app, environ, start_response)
        if not headerinfo:
            for data in result:
                if not data and not headerinfo:
                    continue
                elif not headerinfo:
                    raise WSGIViolation("Data yielded without start_response")
                elif data:
                    result = ResponseWrapper(result, data)
                    break
        if hasattr(result, 'close'):
            closing(result)
        headerinfo.append(result)
        return tuple(headerinfo)
    return mark_lite(maybe_rewrap(app, wrapper))

def _with_write_support(app, environ, _start_response):
    if greenlet is None or not use_greenlets:
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
                greenlet.getcurrent().parent.switch(data)

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
    function that will be called before the wrapped iterator's close().
    """

    def __init__(self, result, first=None, close=None):
        self.first = first
        self.result = result
        if close is not None:
            self._close = close

    def __iter__(self):
        if self.first is not None:
            yield self.first
            self.first = None
        for data in self.result:
            yield data
        self.close()

    def __len__(self):
        return len(self.result)

    _close = _closed = None

    def close(self):
        if self._close is not None:
            self._close()
            del self._close
        if not self._closed:
            self._closed = True
            if hasattr(self.result, 'close'):
                self.result.close()


def wrap_response(result, first=None, close=None):
    if first is None and close is None:
        return result
    return ResponseWrapper(result, first, close)


def get_closer(environ, chain=None):
    """Add a ``wsgi_lite.closing`` key and return a callback or None"""

    if 'wsgi_lite.closing' not in environ:

        cleanups = []
        def closing(item):
            cleanups.append(item)
            return item

        environ['wsgi_lite.closing'] = closing

        def close():
            while cleanups:
                # XXX how to trap errors and clean up from these?
                cleanups.pop().close()
        return close


# Self-replacing stubs for binding support:
def make_stub(name):
    def stub(*args, **kw):
        func = globals()[name] = f = getattr(__import__('wsgi_bindings'),name)
        return f(*args, **kw)
    globals()[name] = stub

make_stub('with_bindings')
make_stub('rebinder')







