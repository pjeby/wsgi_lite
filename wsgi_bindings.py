__all__ = ['bind', 'with_bindings', 'iter_bindings']

from wsgi_lite import maybe_rewrap, renamed, function
import inspect
basestring = getattr(__builtins__, 'basestring', str)

def iter_bindings(rule, environ):
    """Yield possible matches of binding rule `rule` against `environ`

    A `rule` may be a string (instance of type ``str``), an object with a
    ``__wsgi_bind__`` method, a callable, or an iterable.
    
    If a string, it's looked up in `environ`, and the result yielded if found.
    If it has a ``__wsgi_bind__`` method, it's called (passing in the environ),
    and the result iterated over.  (That is, the result must be a sequence or
    generator, possibly empty.)  If the rule doesn't have a ``__wsgi_bind__``
    method, but is callable, it's called in the same way.

    Otherwise, if the rule has an ``__iter__`` method, it's looped over, and
    each element is treated as a rule, recursively, and this function yields
    all of the results.
    """
    if type(rule) is str:
        if rule in environ:
            yield environ[rule]
    elif hasattr(rule, '__wsgi_bind__'):
        for result in rule.__wsgi_bind__(environ):
            yield result
    elif callable(rule):
        for result in rule(environ):
            yield result
    elif not isinstance(rule, basestring) and hasattr(rule, '__iter__'):
        for r in rule:
            for result in iter_bindings(r, environ):
                yield result
    else:
        raise TypeError(
            "binding rule %r of %r has no __wsgi_bind__ method and is not"
            " iterable, callable, or string" % (rule, type(rule))
        )

def with_bindings(bindings, app, environ):
    """Call app(environ, **computed_bindings)"""
    args = {}
    for argname, rule in bindings.items():
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
            if argname in kw and bindings[argname] != kw[argname]:
                raise TypeError(
                    "Rebound argument %r from %r to %r" %
                    (argname, bindings[argname], kw[argname])
                )
        bindings.update(kw)
        if isinstance(f, function):
            argnames = inspect.getargspec(f)[0]
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
        def wrapper(func, environ):
            return with_bindings(bindings, func, environ)
        wrapper = maybe_rewrap(func, wrapper)
        wrapper.__wl_bind_info__ = func, bindings
        return wrapper
    return func

def bind(__name__=None, __doc__=None, __module__=None, **kw):
    """Bind environment-based values to function keyword arguments"""
    return rebinder(make_bindable, __name__, __doc__, __module__, **kw)




























