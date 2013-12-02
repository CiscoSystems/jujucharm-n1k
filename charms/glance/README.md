Overview
--------

This charm provides the Glance image service for OpenStack.  It is intended to
be used alongside the other OpenStack components, starting with the Essex
release in Ubuntu 12.04.

Usage
-----

Glance may be deployed in a number of ways.  This charm focuses on 3 main
configurations.  All require the existence of the other core OpenStack
services deployed via Juju charms, specifically: mysql, keystone and
nova-cloud-controller.  The following assumes these services have already
been deployed.

Local Storage
=============

In this configuration, Glance uses the local storage available on the server
to store image data:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller

Swift backed storage
====================

Glance can also use Swift Object storage for image storage.  Swift is often
deployed as part of an OpenStack cloud and provides increased resilience and
scale when compared to using local disk storage.  This configuration assumes
that you have already deployed Swift using the swift-proxy and swift-storage
charms:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance swift-proxy

This configuration can be used to support Glance in HA/Scale-out deployments.

Ceph backed storage
===================

In this configuration, Glance uses Ceph based object storage to provide
scalable, resilient storage of images.  This configuration assumes that you
have already deployed Ceph using the ceph charm:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance ceph

This configuration can also be used to support Glance in HA/Scale-out
deployments.

Glance HA/Scale-out
===================

The Glance charm can also be used in a HA/scale-out configuration using
the hacluster charm:

    juju deploy -n 3 glance
    juju deploy hacluster haglance
    juju set glance vip=<virtual IP address to access glance over>
    juju add-relation glance haglance
    juju add-relation glance mysql
    juju add-relation glance keystone
    juju add-relation glance nova-cloud-controller
    juju add-relation glance ceph|swift-proxy

In this configuration, 3 service units host the Glance image service;
API requests are load balanced across all 3 service units via the
configured virtual IP address (which is also registered into Keystone
as the endpoint for Glance).

Note that Glance in this configuration must be used with either Ceph or
Swift providing backing image storage.

Contact Information
-------------------

Author: Adam Gandelman <adamg@canonical.com>
Report bugs at: http://bugs.launchpad.net/charms
Location: http://jujucharms.com
