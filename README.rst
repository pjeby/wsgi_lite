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
``write()``, or expect to have a ``close()`` method called.

The ``@lite`` decorator then wraps the function in such a way that if it's
called by a WSGI 1 server or middleware, it will act like a WSGI 1 application.
But if it's called with just an `environ` (i.e., without a ``start_response``),
it'll be just like you called the decorated function directly: that is,
you'll get back a (`status`, `headers`, `body`) triplet.

Pretty neat, eh?  But the real magic comes in with the second decorator,
``lighten()``.  ``lighten()`` accepts either a ``@lite`` application or a
WSGI 1 application, and returns a similarly flexible application object.  Just
like the output of the ``@lite`` decorator, the resulting app object can be
called with or without a ``start_response``, and the protocol it follows will
vary accordingly.

This means that you can either pass a ``@lite`` app or a standard WSGI app
to our ``latinator()`` middleware, and it'll work either way.  And, for
efficiency, both ``@lite`` and ``lighten()`` are designed to be idempotent:
calling them on already-converted apps has no effect, and if you call a
wrapped application via its native protocol, no protocol conversion takes
place.


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
code and won't have any of the problems I'm about to introduce you to...
problems that your *existing WSGI apps already have*, but you probably don't
know about yet!

(People often object when I say that typical application code should **never**
produce its output incrementally...  but the hard problem of proper resource
cleanup when doing so, is one of the reasons I'm always saying it.)

Anyway, if you *must* produce your response in chunks, *and* you need to
release some resources as soon as the response is finished,  you need to use
the ``@wsgi_lite.with_closing`` decorator, e.g::

    @lite
    @with_closing
    def my_app(environ):

        def my_body():
            try:
                # allocate some resources
                ...
                yield chunk
                ...
            finally:
                # release the resources

        return status, headers, my_body()

The ``@with_closing`` decorator takes care of registering your iterator so that
its ``close()`` method will be called at the end of the request, even if the
browser disconnects or a piece of middleware throws away your iterator to use
its own instead.

Yes, that was *all* the bad news.  You need a decorator, that's all.  The rest
of this section is all about what will happen if you *don't* use the decorator,
or if you try to do resource cleanup in a standard WSGI app without the benefit
of WSGI Lite.

As long as you use the decorator, your app's resource cleanup will work *at
least* as well as -- and probably much better than! -- it would work under
plain WSGI.  (And you can make it work even better still if you wrap your
entire WSGI stack with a ``lighten()`` call...  but more on that will have to
wait until the end of this section.)

So, just to be clear, the rest of this section is about flaws and weaknesses
that exist in *standard* WSGI's resource management protocol, and what WSGI
Lite is doing to work around them.

What flaws and weaknesses?  Well, consider the example above.  Why does it
*need* the ``@with_closing`` decorator?  After all, doesn't Python guarantee
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

Otherwise, just use ``@with_closing`` if you need resource cleanup in your
body iterator, and be happy that you don't need to know anything more.  ;-)

Well, actually, you do need to know ONE more thing...  If your outermost
``@lite`` application is wrapped by any off-the-shelf WSGI middleware, you
probably want to wrap the outermost piece of middleware with a ``lighten()``
call.

This will let WSGI Lite make sure that *your* ``close()`` methods get called,
even if the middleware that wraps you is broken.

(Technically speaking, of course, there's no way to be *sure* you're not being
wrapped by middleware, so it's not really a cure-all unless your WSGI server
natively supports the extension described in the next section.  Hopefully,
though, we'll put the extension into a PEP soon and all the popular servers
will provide it.)


The ``wsgi_lite.register_close`` Extension
------------------------------------------

WSGI Lite uses a WSGI server extension called ``wsgi_lite.register_close``,
that lives in the application's `environ` variable.  The ``@lite`` decorator
automatically adds this extension to the environment, if it's called from a
WSGI 1 server or middleware, and the key doesn't already exist.

The value for this key is a callback function that takes one argument: an
object whose ``close()`` method is to be called at the end of the request.  The
idea is that a server (or middleware component) accepts these registrations,
and then closes all the resources (or generators) when the request is finished.

Objects are closed in the order in which they're registered, so that inner
apps' resources are released prior to middleware resources being released.
(That is, so that if an app is using a resource that was obtained via
middleware, the resource will still be usable during the app's finalization.)

Objects registered with this extension **must** have ``close()`` methods, and
the methods **must** be idempotent: that is, it must be safe to call them
more than once.  (That is, calling ``close()`` a second time **must not**
raise an error.)

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
without using ``@with_closing``...  don't.  ;-)

(Unless, of course, you *like* trying to remember a zillion details that must
be gotten perfectly correct if you don't want the whole thing to be silently
pointless.)

Okay, maybe there's some reason you just *have* to use the extension directly
instead of the decorator.  Here's what you need to remember:

 * The WSGI spec allows called applications to modify the `environ`.  This
   means that you **must** retrieve the extension *before* you pass the
   `environ` to another app.

 * Since you don't usually have the object with the ``close()`` method ready
   until near the end of request processing, *and* because the resources might
   be used by any apps you call, you **should** wait until after the child
   request has had a chance to register its resources, before you register
   yours.

These two requirements are in fundamental conflict: you must *retrieve* the
extension as early as possible, but *use* it as late as possible.  And there
are all kinds of goofy corner cases you can run into if you register resources
individually as you go, instead of just putting them all in a nice generator
with ``try/finally``  blocks.

So, that's why we have ``@with_closing``, if you really wanted to know.  It
fetches the extension early, and calls it late.  And it not-so-subtly
discourages you from trying to mess around with registering individual
resources, which is really *really* hard to get right by doing it in a
low-level fashion, even if you have the entire WSGI spec loaded into your
brain's L1 cache!  ;-)


Other Protocol Details
----------------------

Technically, WSGI Lite is a protocol as well as an implementation.  And there's
one other thing besides the Rack-style calling convention and ``register_close``
extension that distinguishes it from standard WSGI.  

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
*whether* to call it.)  

Anyway, the rest of the protocol is defined simply as a stripped down WSGI,
minus ``start_response()``, ``write()``, and ``close()``, but with the addition
of the ``wsgi_lite.register_close`` key.  That's pretty much it.


Limitations
-----------

You knew there had to be a catch, right?

Well, in this case, there are two.

First, if you ``lighten()`` a standard WSGI app that uses ``write()`` calls
instead of using a response iterator, you **must** have the ``greenlet``
library installed, or you'll get an error when ``write()`` is called.

Why?  Well, it's complicated.  But the chances are pretty good that you don't
have any code that uses ``write()``, and if you do, well, ``greenlet`` works on
lots of platforms and Python versions.

And second, speaking of Python versions, if you're using a version less than
2.5, you need to have ``DecoratorTools`` installed as well.  Python 2.4 doesn't
have ``functools`` in the standard library.)

Second, no, third...  wait, I'll come in again.

*Chief* amongst the limitations of WSGI Lite is that it cannot work around
broken WSGI 1 middleware that lives *above* your application in the call stack!

So, until standard WSGI servers support the ``wsgi_lite.register_close``
extension, you can (and should) work around this by putting wrapping your
outermost middleware with a ``lighten()`` call.


Current Status
--------------

The code in this repository is experi-mental, and possibly very-mental or
just plain detri-mental.  It is not tested in any serious way as yet, or even
a non-serious way.  I've thrown this out there for people to see and play with
early.  Stuff may change, break, or this could all have been a really stupid
idea that doesn't actually work.  You have been warned.

(Oh, and it's under an ASF license, since that's what the PSF uses for
contributions... i.e., I anticipate this potentially becoming PEPpable and
stdlib-able in the future, if we don't find some sort of glaring hole in it.)

