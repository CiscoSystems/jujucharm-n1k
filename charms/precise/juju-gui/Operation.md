<!--
Operation.md
Copyright 2013 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm Operation #

## How it works ##

The Juju GUI is a client-side, JavaScript application that runs inside a
web browser. The browser connects to a built-in server deployed by the
charm.

## Server ##

The server directly serves static files to the browser, including
images, HTML, CSS and JavaScript files via an HTTPS connection to port
443. HTTP connections to port 80 are redirected to the former one.
All other URLs serve the common `index.html` file.

It also acts as a proxy between the browser and the Juju API server that
performs the actual orchestration work. Both browser-server and server-
Juju connections are bidirectional, using the WebSocket protocol on the
same port as the HTTPS connection, allowing changes in the Juju
environment to be propagated and shown immediately by the browser.

## Activation ##

Previously the Juju GUI has been served by a combination of haproxy and
Apache, specifically deployed and configured by the charm.

The new built-in server replaces them both and can be enabled by
setting the config option `builtin-server` to `true`.

In the future haproxy, Apache and the mentioned config option will be
removed; only the built-in server will remain.
