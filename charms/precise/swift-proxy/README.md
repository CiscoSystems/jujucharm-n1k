Overview
--------

This charm provides the swift-proxy component of the OpenStack Swift object
storage system.  It can be deployed as part of its own stand-alone storage
cluster or it can be integrated with the other OpenStack components, assuming
those are also managed by Juju.  For Swift to function, you'll also need to
deploy additional swift-storage nodes using the cs:precise/swift-storage
charm.

For more information about Swift and its architecture, visit the [official project website](http://swift.openstack.org)

This charm was developed to support deploying multiple version of Swift on
Ubuntu Precise 12.04, as they relate to the release series of OpenStack.  That
is, OpenStack Essex corresponds to Swift 1.4.8 while OpenStack Folsom shipped
1.7.4.  This charm can be used to deploy either (and future) versions of Swift
onto an Ubuntu Precise 12.04, making use of the Ubuntu Cloud Archive when
needed.

Usage
-----

Currently, Swift may be deployed in two ways.   In either case, additional
storage nodes are required.  The configuration option that dictates
how to deploy this charm is the 'zone-assignment' setting.  This section
describes how to select the appropriate zone assignment policy, as well as
a few other configuration settings of interest.  Many of the configuration
settings can be left as default.

**Zone Assignment**

This setting determines how the charm assigns new storage nodes to storage
zones.

The default, 'manual' option is suggested for production as it allows
administrators to carefully architect the storage cluster.  It requires each
swift-storage service to be deployed with an explicit storage zone configured
in its deployment settings.  Upon relation to a swift-proxy, the storage node
will request membership to its configured zone and be assigned by the
swift-proxy charm accordingly.  Using the cs:precise/swift-storage charm with
this charm, a deployment would look something like:

    $ cat >swift.cfg <<END
        swift-proxy:
            zone-assignment: manual
            replicas: 3
        swift-storage-zone1:
            zone: 1
            block-device: /etc/swift/storage.img|2G
        swift-storage-zone2:
            zone: 2
            block-device: /etc/swift/storage.img|2G
        swift-storage-zone3:
            zone: 3
            block-device: /etc/swift/storage.img|2G
    END
    $ juju deploy --config=swift.cfg swift-proxy
    $ juju deploy --config=swift.cfg swift-storage swift-storage-zone1
    $ juju deploy --config=swift.cfg swift-storage swift-storage-zone2
    $ juju deploy --config=swift.cfg swift-storage swift-storage-zone3
    $ juju add-relation swift-proxy swift-storage-zone1
    $ juju add-relation swift-proxy swift-storage-zone2
    $ juju add-relation swift-proxy swift-storage-zone3

This will result in a configured storage cluster of 3 zones, each with one
node.  To expand capacity of the storage system, nodes can be added to specific
zones in the ring.

    $ juju add-unit swift-storage-zone1
    $ juju add-unit -n5 swift-storage-zone3    # Adds 5 units to zone3

This charm will not balance the storage ring until there are enough storage
zones to meet its minimum replica requirement, in this case 3.

The other option for zone assignment is 'auto'.  In this mode, swift-proxy
gets a relation to a single swift-storage service unit.  Each machine unit
assigned to that service unit will be distributed evenly across zones.

    $ cat >swift.cfg <<END
    swift-proxy:
        zone-assignment: auto
        replicas: 3
    swift-storage:
        zone: 1
        block-device: /etc/swift/storage.img|2G
    END
    $ juju deploy --config=swift.cfg swift-proxy
    $ juju deploy --config=swift.cfg swift-storage
    $ juju add-relation swift-proxy swift-storage
    # The swift-storage/0 unit ends up the first node in zone 1
    $ juju add-unit swift-storage
    # swift-storage/1 ends up the first node in zone 2.
    $ juju add-unit swift-storage
    # swift-storage/2 is the first in zone 3, replica requirement is satisfied
    # the ring is balanced.

Extending the ring in the case is just a matter of adding more units to the
single service unit.  New units will be distributed across the existing zones.

    $ juju add-unit swift-storage
    # swift-storage/3 is assigned to zone 1.
    $ juju add-unit swift-storage
    # swift-storage/4 is assigned to zone 2.
    etc.

**Installation repository.**

The 'openstack-origin' setting allows Swift to be installed from installation
repositories and can be used to setup access to the Ubuntu Cloud Archive
to support installing Swift versions more recent than what is shipped with
Ubuntu 12.04 (1.4.8).  For more information, see config.yaml.

**Authentication.**

By default, the charm will be deployed using the tempauth auth system.  This is
a simple and not-recommended auth system that functions without any external
dependencies.  See Swift documentation for details.

The charm may also be configured to use Keystone, either manually (via config)
or automatically via a relation to an existing Keystone service using the
cs:precise/keystone charm.  The latter is preferred, however, if a Keystone
service is desired but it is not managed by Juju, the configuration for the
auth token middleware can be set manually via the charm's config.  A relation
to a Keystone server via the identity-service interface will configure
swift-proxy with the appropriate credentials to make use of Keystone and is
required for any integration with other OpenStack components.

**Glance**

Swift may be used to as a storage backend for the Glance image service.  To do
so, simply add a relation between swift-proxy and an existing Glance service
deployed using the cs:precise/glance charm.
