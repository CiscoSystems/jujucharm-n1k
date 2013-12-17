Overview
========

Ceph is a distributed storage and network file system designed to provide
excellent performance, reliability and scalability.

This charm deploys the RADOS Gateway, a S3 and Swift compatible HTTP gateway
for online object storage on-top of a ceph cluster.

Usage
=====

In order to use this charm, it is assumed that you have already deployed a ceph
storage cluster using the 'ceph' charm with something like this::

   juju deploy -n 3 --config ceph.yaml ceph

To deploy the RADOS gateway simple do::

   juju deploy ceph-radosgw
   juju add-relation ceph-radosgw ceph

You can then directly access the RADOS gateway by exposing the service::

   juju expose ceph-radosgw

The gateway can be accessed over port 80 (as show in juju status exposed
ports).

Access
======

Note that you will need to login to one of the service units supporting the
ceph charm to generate some access credentials::

   juju ssh ceph/0 \
      'sudo radosgw-admin user create --uid="ubuntu" --display-name="Ubuntu Ceph"'

For security reasons the ceph-radosgw charm is not set up with appropriate
permissions to administer the ceph cluster.

Keystone Integration
====================

Ceph >= 0.55 integrates with Openstack Keystone for authentication of Swift requests.

This is enabled by relating the ceph-radosgw service with keystone::

   juju deploy keystone
   juju add-relation keystone ceph-radosgw

If you try to relate the radosgw to keystone with an earlier version of ceph the hook
will error out to let you know.

Scale-out
=========

Its possible to scale-out the RADOS Gateway itself::

   juju add-unit -n 2 ceph-radosgw

and then stick a HA loadbalancer on the front::

   juju deploy haproxy
   juju add-relation haproxy ceph-radosgw

Should give you a bit more bang on the front end if you really need it.

Contact Information
===================

Author: James Page <james.page@ubuntu.com>
Report bugs at: http://bugs.launchpad.net/charms/+source/ceph-radosgw/+filebug
Location: http://jujucharms.com/charms/ceph-radosgw

Bootnotes
=========

The Ceph RADOS Gateway makes use of a multiverse package libapache2-mod-fastcgi.
As such it will try to automatically enable the multiverse pocket in
/etc/apt/sources.list.  Note that there is noting 'wrong' with multiverse
components - they typically have less liberal licensing policies or suchlike.
