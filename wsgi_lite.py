__all__ = [
    'lite', 'lighten', 'is_lite', 'mark_lite', 'WSGIViolation',
]

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
    while g:
        v = g.switch()
        if v is not None:
            yield v

from new import function
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


def iter_bindings(rule, environ):
    """Yield possible matches of binding rule `rule` against `environ`

    A `rule` may be a string (``basestring`` instance), callable, or iterable.
    If a string, it's looked up in `environ`, and the result yielded if found.
    If it's a callable, it's invoked on the environ, and the result iterated
    over.  (That is, the callable must return a possibly-empty sequence.)
    Otherwise, if the rule has an ``__iter__`` method, it's looped over, and
    each element is treated as a rule, recursively.
    """
    if isinstance(rule, basestring):
        if rule in environ:
            yield environ[rule]
    elif callable(rule):
        for result in rule(environ):
            yield result
    elif hasattr(rule, '__iter__'):
        for r in rule:
            for result in iter_bindings(r, environ):
                yield result
    else:
        raise TypeError(
            "@bind value %r is not a tuple, callable, or string" % (v,)
        )

















def bind(__name__=None, __doc__=None, __module__=None, **kw):
    """Bind environ keys to keyword arguments"""

    if isinstance(__name__, function) or not kw:
        raise TypeError("Usage is @bind(argname='environ key',...)")

    def decorate(func):
        def wrapper(environ, **args):
            for argname, rule in kw.iteritems():
                for value in iter_bindings(rule, environ):
                    args[argname] = value
                    break   # take only first matching value, if any
            return func(environ, **args)

        if is_lite(func):
            raise TypeError("This decorator must be placed *after* @lite")

        if isinstance(func, function):
            if func.func_code is wrapper.func_code:
                (inner_kw, func) = func.__wsgilite_binding__
                for k in inner_kw:
                    if k in kw:
                        raise TypeError(
                            "Rebound argument %r from %r to %r" %
                            (k, inner_kw[k], kw[k])
                        )
                kw.update(inner_kw) 
        if isinstance(func, function):
            argnames = func.func_code.co_varnames[:func.func_code.co_argcount]
            for k in kw:
                if k not in argnames:
                    raise TypeError("%r has no %r argument" % (func, k))            
        wrapper = maybe_rewrap(func, wrapper)
        wrapper.__wsgilite_binding__ = kw, func
        
    decorate = renamed(decorate, __name__ or 'with_'+'_'.join(kw))
    decorate.__doc__ = __doc__
    decorate.__module__ = __module__
    return decorate


class WSGIViolation(AssertionError):
    """A WSGI protocol violation has occurred"""


def lite(__name__=None, __doc__=None, __module__=None, **kw):
    """Wrap a WSGI Lite app for possible use in a plain WSGI server"""
    isfunc = isinstance(__name__, function)
    if kw:
        if isfunc:
            return lite(bind(**kw)(__name__))
        else:
            return bind(__name__, __doc__, __module__, **kw)
    app = __name__
    if not isfunc:
        raise TypeError("Not a function: %r" % (app,))
    elif __doc__ is not None or __module__ is not None:
        raise TypeError(
            "Usage: @lite or @lite(**kw) or lite(name,doc,module,**kw)"
        )
    if is_lite(app):
        # Don't wrap something that supports wsgi_lite already
        return app

    def wrapper(environ, start_response=None):
        if start_response is None:
            # Called via lite, just pass through as-is
            return app(environ) 

        # Support wsgi_lite.add_cleanup() callback
        close = get_closer(environ)                
        s, h, b = app(environ)
        start_response(s, h)
        return wrap_response(b, close=close)

    return mark_lite(maybe_rewrap(app, wrapper))






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
        def write(data):
            raise NotImplementedError("Greenlets are disabled or missing")

        def start_response(status, headers, exc_info=None):
            if headerinfo and not exc_info:
                raise WSGIViolation("Headers already set & no exc_info given")
            headerinfo[:] = status, headers
            return write

        register = environ['wsgi_lite.closing']
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
            register(result)

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
                write(data)

    # save in result so write() knows it 
    result = greenlet(wrap).switch()    
    return result

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


















