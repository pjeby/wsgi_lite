__all__ = ['bind', 'with_bindings', 'iter_bindings']

from wsgi_lite import maybe_rewrap, renamed, function

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
            "binding %r is not a tuple, callable, or string" % (v,)
        )

def with_bindings(bindings, app, environ):
    """Call app(environ, **computed_bindings)"""
    args = {}
    for k, v in bindings.iteritems():
        for argname, rule in kw.iteritems():
            for value in iter_bindings(rule, environ):
                args[argname] = value
                break   # take only first matching value, if any            
    if args:
        return app(environ, **args)
    return app(environ)

def rebinder(decorator, __name__=None, __doc__=None, __module__=None, **kw):
    """Bind environ keys to keyword arguments on a lite-wrapped app"""

    def decorate(func):
        func = decorator(func)
        f, bindings = func.__wl_bind_info__
        for argname in bindings:
            if argname in kw:
                raise TypeError(
                    "Rebound argument %r from %r to %r" %
                    (argname, bindings[argname], kw[argname])
                )
        bindings.update(kw)
        if isinstance(f, function):
            argnames = f.func_code.co_varnames[:f.func_code.co_argcount]
            for argname in kw:
                if argname not in argnames:
                    raise TypeError("%r has no %r argument" % (f, argname))            
        return func
        
    decorate = renamed(decorate, __name__ or 'with_'+'_'.join(kw))
    decorate.__doc__ = __doc__
    decorate.__module__ = __module__
    return decorate

def make_bindable(func):
    if not hasattr(func, '__wl_bind_info__'):
        bindings = {}
        def wrapper(environ):
            return with_bindings(bindings, func, environ)
        wrapper = maybe_rewrap(func, wrapper)
        wrapper.__wl_bind_info__ = func, bindings
        return wrapper
    return func

def bind(__name__=None, __doc__=None, __module__=None, **kw):
    """Bind environment-based values to function keyword arguments"""
    return rebinder(make_bindable, __name__, __doc__, __module__, **kw)



