==========================================
Creating Simpler Middleware with WSGI Lite
==========================================

Wouldn't it be nice if writing *correct* WSGI middleware was this simple?

::

    >>> from wsgi_lite import lite, lighten
    
    >>> def latinator(app):
    ...     @lite
    ...     def middleware(environ):
    ...         status, headers, body = app(environ)
    ...         for name, value in headers:
    ...             if name.lower() == 'content-type' and value == 'text/plain':
    ...                 break
    ...         else:
    ...             # Not text/plain, pass the request through unchanged 
    ...             return status, headers, body
    ...                 
    ...         # Strip content-length if present, else it'll be wrong
    ...         headers = [
    ...             (name, value) for name, value in headers
    ...                 if name.lower() != 'content-length'
    ...         ]
    ...         return status, headers, (piglatin(data) for data in body)
    ... 
    ...     # Make sure that `app` can be invoked via the Lite protocol, even
    ...     # if it's a standard WSGI 1 app:
    ...     app = lighten(app)  
    ...     return middleware

Using just two decorators, WSGI Lite lets you create correct and compliant
middleware and applications, without needing to worry about ``start_response``,
``write`` and ``close`` calls.  And with those *same* two decorators, it also
lets you manage resources to be released at the end of a request, and
automatically pass in keyword arguments to your apps or middleware that
are obtained from the WSGI environment (like WSGI server extensions or
middleware-supplied parameters).

For more details, check out the `project's home page on BitBucket
<https://bitbucket.org/pje/wsgi_lite/#toc>`_, and scroll down to the table
of contents.

.. _toc:
.. contents:: Table of Contents


Introducing WSGI Lite
---------------------

If you've seen the ``Latinator`` example from the WSGI PEP, you may recall that
it's about three times this much code and needs two classes, just to do the job
right.  And, if you've ever tried to code a piece of middleware like this,
you'll know just how hard it is to do it correctly.

In fact, as the author of the WSGI PEPs, I have almost never seen a single
piece of WSGI middleware that doesn't break the WSGI protocol in some way that
I couldn't find with a minute or two of code inspection.

But the above ``latinator`` middleware is actually a valid piece of WSGI 1.0
middleware, that can *also* be called with a simpler, Rack-like protocol.  And
all of the hard parts are abstracted away into two decorators: ``@lite``
and ``lighten()``.

The ``@lite`` decorator says, "this function is a WSGI application, but it
expects to be called with an `environ` dictionary, and return a (`status`,
`headers`, `body`) triplet.  And it doesn't use ``start_response()``,
``write()``, or expect to have a ``close()`` method called."

The ``@lite`` decorator then wraps the function in such a way that if it's
called by a WSGI 1 server or middleware, it will act like a WSGI 1 application.
But if it's called with just an `environ` (i.e., without a ``start_response``),
it'll be just like you called the decorated function directly: that is,
you'll get back a (`status`, `headers`, `body`) triplet.

Pretty neat, eh?  But the real magic comes in with the second decorator,
``lighten()``.  ``lighten()`` accepts either a ``@lite`` application or a
WSGI 1 application, and returns a similarly flexible application object.  Just
like the output of the ``@lite`` decorator, the resulting app object can be
called with or without a ``start_response``, and the return protocol it follows
will vary accordingly.

This means that you can either pass a ``@lite`` app or a standard WSGI app
to our ``latinator()`` middleware, and it'll work either way.  And, you can
supply a ``@lite`` or ``lighten()``-ed app to any standard WSGI server or
middleware, and it'll Just Work.

For efficiency, both ``@lite`` and ``lighten()`` are designed to be idempotent:
calling them on already-converted applications returns the app you passed in,
with no extra wrapping.  And, if you call a wrapped application via its native
protocol, no protocol conversion takes place - the original app just gets
called without any conversion overhead.  So, feel free to use both decorators
early and often!


WSGI Extensions and Environment Keys
------------------------------------

One of the subtler edge cases that can arise in writing correct middleware is
that when you call another WSGI app, it's allowed to change the `environ` you
pass in.

And what most people don't realize, is that this means it's *not safe* to pull
things out of the environment *after* you call another WSGI app!

For example, take a look at this middleware example::

    def middleware(environ, start_response):
        response = some_app(environ, start_response)
        if environ.get('PATH_INFO','').endswith('foo'):
            # ...  etc.

Think it'll work correctly?  Think again.  If ``some_app`` is a piece of
routing middleware, it could already have changed ``PATH_INFO``, or any other
environment key.  Likewise, if this middleware looks for server extensions
like ``wsgi.file_wrapper`` or ``wsgiorg.routing_args``, it might end up
reading the child application's extensions, rather than those intended for the
middleware itself.

To help handle these cases, the ``@lite`` decorator can bind a function's
keyword arguments to values based on the contents of the `environ` argument::

    @lite(path='PATH_INFO', routing='wsgiorg.routing_args')
    def middleware(environ, path='', routing=((),{})):
        response = some_app(environ, start_response)
        if path.endswith('foo'):
            # ...  etc.

When ``@lite`` is called with keyword arguments whose argument names match
argument names on the decorated function, it wraps the function in such a way
that the matching keys from the `environ` are passed in as keyword arguments.
This automatically ensures that you aren't using possibly-corrupted keys from
your child app(s), *and* lets you specify default values (via your function's
argument defaults, as shown above).

As a convenience for frequently used extensions or keys, you can save
calls to ``lite()`` and give them names, for example::

    >>> with_routing = lite(routing='wsgiorg.routing_args')

And the resulting decorator is precisely equivalent to invoking ``@lite()``
directly::
    
    >>> @with_routing
    ... def middleware(envrion, routing=((),{})):
    ...     """Some sort of middleware"""

You can even stack multiple ``@lite()`` calls (direct or saved), or give them
names, docstrings, and specify what module you defined them in::

    >>> with_path = lite(
    ...     'with_path', "Add a `path` arg for ``PATH_INFO``", "__main__",
    ...     path='PATH_INFO'
    ... )

    >>> help(with_path)
    Help on function with_path in module __main__:
    with_path(func)
        Add a `path` arg for ``PATH_INFO``

    >>> @with_routing
    ... @with_path
    ... def middleware(environ, path='', routing=((),{})):
    ...     """Some combined middleware"""

By the way, the underlying decorator is smart enough to tell when it's being
stacked, and automatically merges the wrappings so there's only one level
of calling overhead added, no matter how many of them you stack.  (As long as
they're not intermingled with other decorators, of course!)

Sometimes, an extension may be known under more than one name - for example,
an ``x-wsgiorg.`` extension vs. a ``wsgiorg.`` one, or a similar extension
provided by different servers.  You could of course bind them to different
arguments, but it's generally simpler to just bind a single argument, using
a tuple::

    >>> @lite(routing=('wsgiorg.routing_args', 'x-wsgiorg.routing_args'))
    ... def middleware(envrion, routing=((),{})):
    ...     """Some sort of middleware"""

This will check the environment for the named extensions in the order listed,
and replace `routing` with the first one matched.

These argument specifications are called "binding rules", by the way.  A rule
is either a string (i.e. an instance of ``basestring``), a callable object, or
an iterable of rules (recursively).  Strings are looked up in the environ, and
iterables are tried in sequence until a lookup succeeds.

Callable rules, on the other hand, are looked up by being called with a
single positional argument: the `environ` dictionary.  They must return an
iterable (or sequence) yielding zero or more items.  Returning an empty
sequence or yielding zero items means the lookup failed, and a default value
should be used instead (or the next alternative binding rule provided for that
keyword argument).  Otherwise, the first item yielded is passed in as the
matching keyword argument.  Here's an example of using a classmethod as a
callable binding rule::

    >>> class MyRequest(object):
    ...     def __init__(self, environ):
    ...         self.environ = environ
    ...
    ...     @classmethod
    ...     def bind(cls, environ):
    ...         yield cls(environ)

    >>> with_request = lite(request=MyRequest.bind)

Now, ``@with_request`` will create a ``MyRequest`` instance wrapping the
`environ` of the decorated function, and provide it via the ``request`` keyword
argument.

The same approach can also be used to do things like accessing
environment-cached objects, such as sessions::

    >>> class MySession(object):
    ...     def __init__(self, environ):
    ...         self.environ = environ
    ...
    ...     @classmethod
    ...     def bind(cls, environ):
    ...         session = environ.get('myframework.MySession')
    ...         if session is None:
    ...             session = environ['myframework.MySession'] = cls(environ)
    ...         yield session

    >>> with_session = lite(session=MySession.bind)

The possibilities are pretty much endless -- and much more in keeping with my
original vision for how WSGI was supposed to help dissolve web frameworks into
*web libraries*.  (That is, things you can easily mix and match without 
every piece of code you use having to come from the same place.)

Callables that you use as bindings don't even have to return something from
the environment or wrap the environment, by the way - they can just be things
that *use* something from the environment.  For example, you could bind
parameters to temporary files that will be automatically closed when the
request is finished::

    >>> def mktemp(environ):
    ...     closing = environ['wsgi_lite.closing']
    ...     yield closing(tempfile(etc[...]))

    >>> @lite(tmp1=mktemp, tmp2=mktemp)
    ... def do_something(environ, tmp1, tmp2):
    ...     """Write stuff to tmp1 and tmp2"""

You can even use argument bindings *in your binding functions*, using the
``@bind`` decorator from the ``wsgi_bindings`` module::

    >>> from wsgi_bindings import bind

    >>> @bind(closing = 'wsgi_lite.closing')
    ... def mktemp(environ, closing):
    ...     yield closing(tempfile(etc[...]))
    
``@bind()`` is just like ``@lite()`` with keyword arguments (including the
ability to save and stack calls), except that it doesn't turn the decorated
function into a WSGI-compatible app.  (Which is a good thing, since a binding
rule is not a WSGI app!)

Now, given the above examples, you might be wondering what all that
``wsgi_lite.closing`` stuff is about.  Well, that's what we're going to talk
about in the next two sections...


``close()`` and Resource Cleanups
---------------------------------

So, there's some good news and some bad news about ``close()`` and resource
cleanups in WSGI Lite.

The *good* news is, ``@lite`` middleware is **not** required to call a body
iterator's ``close()`` method.  And if your app or middleware doesn't need to
do any post-request resource cleanup, or if it just returns a body sequence
instead of an iterator or generator, then you don't need to worry about
resource cleanup at all.  Just write the app or middleware and get on with your
life.  ;-)

Now, if you *are* yielding body chunks from your WSGI apps, you might
want to consider *just not doing that*.

That's because, if you don't yield chunks, you can write normal, synchronous
code that won't have any of the problems I'm about to introduce you to...
problems that your *existing WSGI apps already have*, but you probably don't
know about yet!

(People often object when I say that typical application code should **never**
produce its output incrementally...  but the hard problem of proper resource
cleanup when doing so, is one of the reasons I'm always saying it.)

Anyway, if you *must* produce your response in chunks, *and* you need to
release some resources as soon as the response is finished, you need to use
the ``wsgi_lite.closing`` extension, e.g::

    @lite(closing='wsgi_lite.closing')
    def my_app(environ, closing):

        def my_body():
            try:
                # allocate some resources
                ...
                yield chunk
                ...
            finally:
                # release the resources

        return status, headers, closing(my_body())

This protocol extension (accessed as ``closing()`` in the function body above)
is used to register an iterator (or other resource) so that its ``close()``
method will be called at the end of the request, even if the browser
disconnects or a piece of middleware throws away your iterator to use its own
instead.

An important note: items registered with ``closing()`` are closed in *reverse*
registration order.  This means that if the ``my_body()`` iterator above is
looping over a sub-app's response, then its ``finally`` block may be run
**before** any similar ``finally`` block in the sub-app.  Therefore, your
``finally`` block **must not close** any resources the sub-app might be using!

So, if you are passing any resources down to another WSGI application, be
sure to call ``closing()`` on them *before* calling the other application, and
then *don't* close them in your body iterator.  Example::

    @lite(closing='wsgi_lite.closing')
    def my_app(environ, closing):
        environ['some.key'] = closing(some_resource())
        return subapp(environ)

In other words, you should *only* close resources in your iterator if that's
where they were opened, or you are 100% positive they can't be accessed from
a sub-app.  Otherwise, just call ``closing()`` on them as soon as you allocate
them.

**Don't**, however, call ``closing()`` on objects that don't belong to your
function.  If you didn't allocate it, closing it is somebody else's job.  In
particular, you don't need to call ``closing()`` on any WSGI or WSGI Lite
response bodies, because ``lighten()`` takes care of that for you, and you'll
end up double-closing things.

Okay, so *that* was the bad news.  Not that bad, though, is it?  You just need
to add an extra argument to ``@lite``, pay a little bit of attention to the
order of resource closing, and register your own objects (but *only* your own
objects) for closing.  That's it!

Really, the rest of this section is all about what will happen if you *don't*
use the extension, or if you try to do resource cleanup in a standard WSGI app
without the benefit of WSGI Lite.

As long as you use the extension, your app's resource cleanup will work *at
least* as well as -- and probably much better than! -- it would work under
plain WSGI.  (And you can make it work even better still if you wrap your
entire WSGI stack with a ``lighten()`` call...  but more on that will have to
wait until the end of this section.)

So, just to be clear, the rest of this section is about flaws and weaknesses
that exist in *standard* WSGI's resource management protocol, and what WSGI
Lite is doing to work around them.

What flaws and weaknesses?  Well, consider the example above.  Why does it
*need* the ``closing()`` extension?  After all, doesn't Python guarantee
that the ``finally`` block will be executed anyway?

Well, yes and no.  First off, if the generator is called but never iterated
over, the ``try`` block won't execute, and so neither will the ``finally``.
So, it depends on what the caller does with the generator.  For example, if
the browser disconnects before the body is fully generated, the server might
*just stop iterating* over it.

Okay, but won't garbage collection take care of it, then?

Well, yes and no.  *Eventually*, it'll be garbage collected, but in the
meantime, your app has a resource leak that might be exploitable to deny
service to the app: just start up a resource-using request, then drop the
connection over and over until the server runs out of memory or file handles
or database cursors or whatever.

Now, under the WSGI standard, middleware and servers are *supposed* to call
``close()`` on a response iterator (if it has one), whenever they stop
iterating -- regardless of whether the iteration finished normally, with an
error, or due to a browser disconnect.

In practice, however, **most** WSGI middleware is broken and doesn't call
``close()``, because 1) doing so usually makes your middleware code really
*really* complicated, and 2) nobody understands why they *need* to call
``close()``, because everything *appears* to work fine without it.  (At least,
until some black-hat finds your latent denial-of-service bug, anyway.)

So, WSGI Lite works around this by giving you a way to be *sure* that
``close()`` will be called, using a tiny extension of the WSGI protocol that
I'll explain in the next section...  but only if you care about the details.

Otherwise, just use the ``wsgi_lite.closing`` extension if you need resource
cleanup in your body iterator, and be happy that you don't need to know
anything more.  ;-)

Well, actually, you do need to know ONE more thing...  If your outermost
``@lite`` application is wrapped by any off-the-shelf WSGI middleware, you
probably want to wrap the outermost piece of middleware with a ``lighten()``
call.  This will let WSGI Lite make sure that *your* ``close()`` methods get
called, even if the middleware that wraps you is broken.

(Technically speaking, of course, there's no way to be *sure* you're not being
wrapped by middleware, so it's not really a cure-all unless your WSGI server
natively supports the extension described in the next section.  Hopefully,
though, we'll put the extension into a PEP soon and all the popular servers
will provide it in a reasonable time period.)


The ``wsgi_lite.closing`` Extension
-----------------------------------

WSGI Lite uses a WSGI server extension called ``wsgi_lite.closing``,
that lives in the application's `environ` variable.  The ``@lite`` and
``lighten()`` decorators automatically add this extension to the environment,
if they're called from a WSGI 1 server or middleware, and the key doesn't
already exist.  (This is why you don't need a default value for the ``closing``
argument, by the way: the key will always be available to a ``@lite`` app or
middleware component, or any sub-app or sub-middleware that inherits the same
environment.)

The value for this key is a callback function that takes one argument: an
object whose ``close()`` method is to be called at the end of the request.
For convenience, the passed-in object is returned back to the caller, so you
can use it in a way that's reminiscent of ``with closing(file('foo')) as f:``.

Anyway, the idea here is that a server (or middleware component) accepts these
registrations, and then closes all the resources (or generators) when the
request is finished.

Objects are closed in the reverse order from which they're registered, so that
inner apps' resources are released prior to middleware-provided resources being
released.  (In other words, if an app is using a resource that it received from
middleware via its `environ`, that resource will still be usable during the
app's ``close()`` processing or ``finally`` blocks.)

Objects registered with this extension **must** have ``close()`` methods, and
the methods **must** be idempotent: that is, it must be safe to call them
more than once.  (That is, calling ``close()`` a second time **must not**
raise an error.)

``close()`` methods are explicitly allowed to registering additional objects to
be closed: such objects are effectively "pushed" onto the stack of objects to
be closed, with the last added object being closed first.  (Note that this
implies that a ``close()`` method **must not** directly or indirectly
re-register itself, as this would create an infinite loop of closing calls.)

Currently, the handling of errors raised by ``close()`` methods is undefined,
in that WSGI Lite doesn't yet handle them.  ;-)  (When I have some idea of how
best to handle this, I'll update this bit of the spec.)

I would like to encourage WSGI server developers to support this extension if
they can.  While WSGI Lite implements it via middleware (in both the ``@lite``
and ``lighten()`` decorators), it's best if the WSGI origin server does it,
in order to bypass any broken middleware in between the server and the app.
(And, if a ``@lite`` or ``lighten()`` app is invoked from a server or
middleware that already implements this extension, it'll make use of the
provided implementation, instead of adding its own.)

Now, if for some reason you want to use this extension directly in your code
without using a ``@lite()`` binding, *please* remember that the WSGI spec
allows called applications to modify the `environ`.  This means that you
**must** retrieve the extension *before* you pass the `environ` to another app.
(That's why we *have* keyword binding in ``@lite()``, remember?)


Other Protocol Details
----------------------

Technically, WSGI Lite is a protocol as well as an implementation.  And there's
still one more thing to cover (besides the Rack-style calling convention and
``closing`` extension) that distinguishes it from standard WSGI.  

Applications supporting the "lite" invocation protocol (i.e. being called
without a ``start_response`` and returning a status/header/body triplet), are
identified by a ``__wsgi_lite__`` attribute with a ``True`` value.  (``@lite``
and ``lighten()`` add this for you automatically.)

Any app *without* the attribute, however, is assumed to be a standard WSGI 1
application, and thus in need of being ``lighten()``-ed before it can be
called via the WSGI Lite protocol.

(If you want to check for this attribute, or add it to an object that natively
supports WSGI Lite, you can use the ``wsgi_lite.is_lite()`` and
``wsgi_lite.mark_lite()`` APIs, respectively.  But even if you want to, you
probably don't  *need* to, because if you call ``@lite`` or ``lighten()`` on
an object that's already "lite", it's returned unchanged.  So it's easier to
just always call the appropriate decorator, rather than trying to figure out
*whether* to call it.  Idempotence == **good**!)  

Anyway, the rest of the protocol is defined simply as a stripped down WSGI,
minus ``start_response()``, ``write()``, and ``close()``, but with the addition
of the ``wsgi_lite.closing`` key.  That's pretty much it.


Known Limitations
-----------------

You knew there had to be a catch, right?

Well, in this case, there are three.

First, if you ``lighten()`` a standard WSGI app that uses ``write()`` calls
instead of using a response iterator, you **must** have the ``greenlet``
library installed, or you'll get an error when ``write()`` is called.

Why?  Well, it's complicated.  But the chances are pretty good that you don't
have any code that uses ``write()``, and if you do, well, ``greenlet`` works on
lots of platforms and Python versions.

Anyway, that's the first limitation.  The second limitation is that WSGI Lite
cannot work around broken WSGI 1 middleware that lives *above* your application
in the call stack!  That is, if your code runs under a middleware component
that alters your response, but forgets to make sure your app's response's
``close()`` method gets called, then none of the fancy resource closing
features in WSGI Lite will work properly.

So, until standard WSGI servers support the ``wsgi_lite.closing``
extension, you can (and should) work around this by wrapping your *entire*
WSGI stack with a ``lighten()`` call.  This way, as long as your *server*
isn't broken, it'll call WSGI Lite's closer, and all will be well with your
resource closing.

Third and finally, the ``lighten()`` wrapper doesn't support broken WSGI
apps that call ``write()`` from inside their returned iterators.  While some
servers allow it, the WSGI specification *explicitly* forbids it, and to
support it in WSGI Lite would force *all* wrapped WSGI 1 apps to pay in the
form of unnecessary greenlet context switches, even if they never used
``write()`` at all.

Since the current "word on the street" says that very few WSGI apps use
``write()`` at all, I figure it's okay to blow up on the even smaller number
that are also spec violators, rather than burden *all* apps with extra overhead
just to support the ill-behaved ones.  However, if you feel otherwise, let
me know about it via the Web-SIG.  (Especially if you have a workable
suggestion for how to work around it without making things slower for the
apps that don't call write()!)


Current Status
--------------

The code in this repository is experi-mental, and possibly very-mental or
just plain detri-mental.  It has not been seriously used or battle-hardened
as yet, even though test coverage is now at 100%, and there are some fairly
exhaustive WSGI compliance tests that exercise many obscure corners of the
WSGI protocol.

Ironically enough, however, that may well mean that there is important "WSGI"
code out there that **won't** work with this module yet, precisely because that
other code is *not* compliant with the spec!  So, while this project's code
*should* work quite well for compliant code, this doesn't mean it will play
well with all the code you're using in all your project(s).  Exercise it
carefully, and don't assume that because it works great for one of your apps
or middleware components, it'll therefore work great with all of them!

In general, this is still alpha software, and things may change or break.  It
might even be that the whole thing was a really stupid idea that won't actually
work in the real world for some reason.

So, I've really just thrown this out there for people to see and play with, so
I can get some feedback on its actual usability.  Feel free to drop me an email
via the Web-SIG mailing list, to let me know what you think.  Hopefully, we'll
soon get any glitches sorted out, and nail this down to something that's less
of a moving target, and maybe even turn it into a PEP and a stdlib
contribution!

(Oh, and last, but not least...  this package is under the Apache license,
since that's what the PSF uses for software contributed to Python, and
hopefully that's where this is headed, assuming we don't find some sort of
glaring hole in the protocol or concept, of course, and it's in sufficiently
high demand.)

