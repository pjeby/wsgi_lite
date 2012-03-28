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
    if getattr(app, '__wsgi_lite__', False):
        return True     # Direct declaration       

    # Filter out cases where __call__ is an unbound instance method
    # XXX this doesn't handle random functions tacked onto a classic class!
    call = getattr(app, '__call__', None)
    if getattr(call, '__wsgi_lite__', False) and not isinstance(call, function):
        return not isinstance(call, instancemethod) or \
            getattr(call, 'im_self', getattr(call, '__self__', None)) is app
    return False

def _iter_greenlet(g=None):
    while g:
        v = g.switch()
        if v is not None:
            yield v

from types import FunctionType as function, MethodType as instancemethod   





try:
    from peak.util.proxies import AbstractWrapper
except ImportError:
    # No proxy types?   Sorry, can't use enhanced app attributes
    def CallableProxy(app, wrapped):
        return wrapped
else:
    class CallableProxy(AbstractWrapper):
        """Proxy an object, replacing its __call__ method

        This class (which is only used if the ProxyTypes package is installed)
        allows calling objects like WebOb's Response with the lite protocol via
        ``lighten()``, while still retaining all their enhanced (non-WSGI)
        functionality.

        That is, if you have ProxyTypes installed, and ``lighten()`` a
        non-function WSGI app like a WebOb Response object, you'll still be
        able to use all the regular response methods, *and* call it using the
        Lite protocol instead of WSGI.
        """    
        __slots__ = ["__subject__", "__lite_wrapper__"]
    
        def __init__(self, subject, wrapped):
            self.__subject__ = subject
            object.__setattr__(self, '__lite_wrapper__', wrapped)
    
        def __call__(self, *args):
            wrapper = object.__getattribute__(self, '__lite_wrapper__')
            return wrapper(*args)
    
        def __getattribute__(self, attr):
            if attr == '__wsgi_lite__':
                return True
            return AbstractWrapper.__getattribute__(self, attr)

        def __setattr__(self, attr, val):
            if attr != '__wsgi_lite__' or val is not True:
                return AbstractWrapper.__setattr__(self, attr, val)
            


def maybe_rewrap(app, wrapper, proxy=False):
    def wrapped(*args):
        if args and type(args[0]) is not dict:
            self = args[0]
            args = args[1:]                
            return wrapper(instancemethod(app, self), *args)
        return wrapper(app, *args)
    
    if isinstance(app, function):
        wrapped = renamed(wrapped, app.__name__)
        wrapped.__module__ = app.__module__
        wrapped.__doc__    = app.__doc__
        wrapped.__dict__.update(app.__dict__)
    elif proxy:
        return CallableProxy(app, wrapped)
    return wrapped

def renamed(f, name):
    try:
        f.__name__ = name
    except TypeError:   # 2.3 doesn't allow renames
        f = function(
            f.func_code, f.func_globals, name, f.func_defaults, f.func_closure
        )
    return f

def lite(__name_or_func__=None, __doc__=None, __module__=None, **kw):
    """Wrap a WSGI Lite app for possible use in a plain WSGI server"""
    isfunc = callable(__name_or_func__)

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
    def wrapper(app, environ, start_response=None):
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

def _raise(exc_info):
    try:
        if hasattr(exc_info[1], '__traceback__'):
            exec ("raise exc_info[1].with_traceback(exc_info[2])")
        else:
            exec ("raise exc_info[0], exc_info[1], exc_info[2]")
    finally:
        exc_info = None





class app:
    """Base for types (as opposed to instances) that implement WSGI Lite
    e.g::

        from wsgi_lite import lite
        class MyApp(lite.app):
            def app(self, environ):
                # Actual implementation goes here

    In the above example, ``MyApp`` is a WSGI-compatible app and can be called
    with either the WSGI or WSGI Lite calling protocol.

    Your `app()` method can use @lite or @lite-based decorators if you want it
    to receive bindings.  Also, you can override ``__init__(self, environ)`` to
    access the environment or receive bindings, if you want to do some common
    setup before the app part runs.
    """

    class __metaclass__(type):
        __wsgi_lite__ = True       

        def __call__(cls, environ):
            self = type.__call__(cls, environ)
            return lite(self.app)(environ)
    
        __call__ = lite(__call__)

    def __new__(cls, environ):
        return object.__new__(cls)

    def __init__(self, environ):
        """You can @bind arguments to your __init__, if you like"""
       
    def app(self, environ):
        """Override this to implement your app"""
        raise NotImplementedError(
            "You must define an app() method in your subclass!"
         )
if not isinstance(app, app.__metaclass__): app = app.__metaclass__('app',(),dict(app.__dict__))
lite.app = app

def lighten(app):
    """Wrap a (maybe) non-lite app so it can be called with WSGI Lite"""
    if is_lite(app):
        # Don't wrap something that supports wsgi_lite already
        return app
    def wrapper(app, environ, start_response=None):
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
                    if data: _raise(exc_info)
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
    return mark_lite(maybe_rewrap(app, wrapper, True))

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

def wraps(app, **kw):
    """@lite.wraps(func, **kw) - create method-safe lite-compatible decorators"""
    def wrap(func):
        return maybe_rewrap(app, kw and lite(**kw)(func) or lite(func))
    return wrap 
lite.wraps = wraps

# Self-replacing stubs for binding support:
def make_stub(name):
    def stub(*args, **kw):
        func = globals()[name] = f = getattr(__import__('wsgi_bindings'),name)
        return f(*args, **kw)
    globals()[name] = stub

make_stub('with_bindings')
make_stub('rebinder')


