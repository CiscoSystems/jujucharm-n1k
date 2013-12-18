Overview
========

The OpenStack Dashboard provides a Django based web interface for use by both
administrators and users of an OpenStack Cloud.

It allows you to manage Nova, Glance, Cinder and Neutron resources within the
cloud.

Usage
=====

The OpenStack Dashboard is deployed and related to keystone:

    juju deploy openstack-dashboard
    juju add-unit openstack-dashboard keystone

The dashboard will use keystone for user authentication and authorization and
to interact with the catalog of services within the cloud.

The dashboard is accessible on:

    http(s)://service_unit_address/horizon

At a minimum, the cloud must provide Glance and Nova services.

SSL configuration
=================

To fully secure your dashboard services, you can provide a SSL key and
certificate for installation and configuration.  These are provided as
base64 encoded configuration options::

    juju set openstack-dashboard ssl_key="$(base64 my.key)" \
        ssl_cert="$(base64 my.cert)"

The service will be reconfigured to use the supplied information.

High Availability
=================

The OpenStack Dashboard charm supports HA in-conjunction with the hacluster
charm:

    juju deploy hacluster dashboard-hacluster
    juju set openstack-dashboard vip="192.168.1.200"
    juju add-relation openstack-dashboard dashboard-hacluster
    juju add-unit -n 2 openstack-dashboard

After addition of the extra 2 units completes, the dashboard will be
accessible on 192.168.1.200 with full load-balancing across all three units.

Please refer to the charm configuration for full details on all HA config
options.


Use with a Load Balancing Proxy
===============================

Instead of deploying with the hacluster charm for load balancing, its possible
to also deploy the dashboard with load balancing proxy such as HAProxy:

    juju deploy haproxy
    juju add-relation haproxy openstack-dashboard
    juju add-unit -n 2 openstack-dashboard

This option potentially provides better scale-out than using the charm in
conjunction with the hacluster charm.
