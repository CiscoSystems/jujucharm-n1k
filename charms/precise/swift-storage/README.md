Overview
--------

This charm provides the swift-storage component of the OpenStack Swift object
storage system.  It can be deployed as part of its own standalone storage
cluster or it can be integrated with the other OpenStack components, assuming
those are also managed by Juju.  For Swift to function, you'll also need to
deploy an additional swift-proxy using the cs:precise/swift-proxy charm.

For more information about Swift and its architecture, visit the official
project website at http://swift.openstack.org.

This charm was developed to support deploying multiple version of Swift on
Ubuntu Precise 12.04, as they relate to the release series of OpenStack.  That
is, OpenStack Essex corresponds to Swift 1.4.8 while OpenStack Folsom shipped
1.7.4.  This charm can be used to deploy either (and future) versions of Swift
onto an Ubuntu Precise 12.04, making use of the Ubuntu Cloud Archive when
needed.

Usage
-----

This charm is quite simple.  Its basic function is to get a storage device
setup for swift usage, and run the container, object and account services.
The deployment workflow for swift using this charm is covered in the README
for the swift-proxy charm at cs:precise/swift-proxy.  The following are
deployment options to take into consideration when deploying swift-storage.

**Zone assignment**

If the swift-proxy charm is configured for manual zone assignment (recommended),
the 'zone' option should be set for each swift-storage service being deployed.
See the swift-proxy README for more information about zone assignment.

**Storage**

Swift storage nodes require access to local storage and filesystem.  The charm
takes a 'block-device' config setting that can be used to specify which storage
device(s) to use.  Options include:

 - 1 or more local block devices (eg, sdb or /dev/sdb).  It's important that this
   device be the same on all machine units assigned to this service.  Multiple
   block devices should be listed as a space-separated list of device nodes.
 - a path to a local file on the filesystem with the size appended after a pipe,
   eg "/etc/swift/storagedev1.img|5G".  This will be created if it does not
   exist and be mapped to a loopback device. Good for development and testing.
 - "guess" can be used to tell the charm to do its best to find a local devices
   to use. *EXPERIMENTAL*

Multiple devices can be specified. In all cases, the resulting block device(s)
will each be formatted as XFS file system and mounted at /srv/node/$devname.

**Installation repository**

The 'openstack-origin' setting allows Swift to be installed from installation
repositories and can be used to setup access to the Ubuntu Cloud Archive
to support installing Swift versions more recent than what is shipped with
Ubuntu 12.04 (1.4.8).  For more information, see config.yaml.
