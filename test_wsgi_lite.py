def piglatin(text):
    """Quick and dirty, regex-based pig latin converter"""
    pl_re="""
    (?ix)       # Verbose processing, ignore case
    (\W|^)      # Start of word or string
    (?! (?: the|\w{0,2})(?:\W|$)) # Don't match 'the' or two-letter words
    (\w*?)([aeiouy]\w*)
    (?= \W|$)   # End of word or string
    """
    import re
    def cvt(m):
        pre, head, tail = m.groups()
        return pre+tail+(head or 'w')+'ay'
    return re.sub(pl_re, cvt, text)
    

def latinator(app):
    from wsgi_lite import lite, lighten

    def middleware(environ):
        status, headers, body = app(environ)
        for name, value in headers:
            if name.lower() == 'content-type' and value == 'text/plain':
                break
        else:
            # Not text/plain, pass it through unchanged 
            return status, headers, body
                
        # Strip content-length if present, else it'll be wrong
        headers = [
            (name, value) for name, value in headers
                if name.lower() != 'content-length'
        ]
        def pliter(body):   # Python 2.3 doesn't do generator expressions
            for data in body: yield piglatin(data)
        return status, headers, pliter(body)

    # Make sure that `app` can be invoked via the Lite protocol
    app = lighten(app)  
    return lite(middleware)

def test(app, environ={}, form={}, _debug=True, **kw):
    """Print the output of a WSGI app

    Runs `app` as a WSGI application and prints its output.  If an untrapped
    error occurs in `app`, it drops into the ``pdb`` debugger's post-mortem
    debug shell (using ``sys.__stdout__`` if ``sys.stdout`` has been replaced).

    Any keyword arguments are added to the environment used to run `app`.  If
    a keyword argument begins with ``wsgi_``, the ``_`` is replaced with a
    ``.``, so that you can set e.g. ``wsgi.multithread`` using a
    ``wsgi_multithread`` keyword argument.

    If a non-empty `form` dictionary is provided, it is treated as a collection
    of fields for a form ``POST``. The ``REQUEST_METHOD`` will default to
    ``POST``, and the default ``CONTENT_LENGTH``, ``CONTENT_TYPE``, and
    ``wsgi.input`` values will be appropriately set (but can still be
    overridden by explicit keyword arguments or the `environ` argument).

    Any `form` values that are not instances of ``basestring`` are assumed to
    be *sequences* of values, and will result in multiple name/value pairs
    being added to the encoded data sent to the application.

    Any WSGI-required variables that are not specified by `environ`, `form`, or
    keyword arguments, are initialized to default values using the
    ``wsgiref.util.setup_testing_defaults()`` function.
    """
    import sys
    from wsgiref.util import setup_testing_defaults
    from wsgiref.handlers import BaseCGIHandler
    from StringIO import StringIO
    from urllib import quote_plus

    environ = environ.copy()
    for k, v in kw.items():
        if k.startswith('wsgi_'):
            environ[k.replace('_','.',1)] = v
        else:
            environ[k] = v



    if form:
        encoded = []
        for k, v in form.items():
            if isinstance(v,basestring):
                v = [v]
            for v in v:
                encoded.append('%s=%s' % (quote_plus(k), quote_plus(v)))
        encoded = '&'.join(encoded)
        environ.setdefault('wsgi.input', StringIO(encoded))
        environ.setdefault('CONTENT_LENGTH', str(len(encoded)))
        environ.setdefault('CONTENT_TYPE', 'application/x-www-form-urlencoded')
        environ.setdefault('REQUEST_METHOD', 'POST')

    setup_testing_defaults(environ)
    stdout = StringIO()
    stderr = environ['wsgi.errors']
    def wrapper(env, start):
        try:
            return app(env, start)
        except:
            if _debug:
                stdout = sys.stdout
                try:
                    if stdout is not sys.__stdout__:
                        sys.stdout = sys.__stdout__
                    import pdb
                    pdb.post_mortem(sys.exc_info()[2])
                finally:
                    sys.stdout = stdout
            raise

    BaseCGIHandler(
        environ['wsgi.input'], stdout, stderr, environ,
        environ['wsgi.multithread'], environ['wsgi.multiprocess']
    ).run(wrapper)
    print stdout.getvalue().replace('\r\n','\n')
    if stderr.getvalue():
        print "--- Log Output ---"
        print stderr.getvalue().replace('\r\n','\n')


def additional_tests():
    tests = ['tests.txt']
    try:
        from greenlet import greenlet
    except ImportError:
        pass
    else:
        tests.append('greenlet-tests.txt')

    import doctest
    return doctest.DocFileSuite(
        optionflags = doctest.ELLIPSIS
                    | doctest.NORMALIZE_WHITESPACE
                    | doctest.REPORT_ONLY_FIRST_FAILURE,
        *tests
    )

























