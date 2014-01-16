Overview
--------

Neutron provides flexible software defined networking (SDN) for OpenStack.

This charm is designed to be used in conjunction with the rest of the OpenStack
related charms in the charm store) to virtualized the network that Nova Compute
instances plug into.

Its designed as a replacement for nova-network; however it does not yet
support all of the features as nova-network (such as multihost) so may not
be suitable for all.

Neutron supports a rich plugin/extension framework for propriety networking
solutions and supports (in core) Nicira NVP, NEC, Cisco and others...

The Openstack charms currently only support the fully free OpenvSwitch plugin
and implements the 'Provider Router with Private Networks' use case.

See the upstream [Neutron documentation](http://docs.openstack.org/trunk/openstack-network/admin/content/use_cases_single_router.html)
for more details.


Usage
-----

In order to use Neutron with Openstack, you will need to deploy the
nova-compute and nova-cloud-controller charms with the network-manager
configuration set to 'Neutron':

    nova-cloud-controller:
        network-manager: Neutron

This decision must be made prior to deploying Openstack with Juju as
Neutron is deployed baked into these charms from install onwards:

    juju deploy nova-compute
    juju deploy --config config.yaml nova-cloud-controller
    juju add-relation nova-compute nova-cloud-controller

The Neutron Gateway can then be added to the deploying:

    juju deploy quantum-gateway
    juju add-relation quantum-gateway mysql
    juju add-relation quantum-gateway rabbitmq-server
    juju add-relation quantum-gateway nova-cloud-controller

The gateway provides two key services; L3 network routing and DHCP services.

These are both required in a fully functional Neutron Openstack deployment.

If multiple floating pools are needed then an L3 agent (which corresponds to
a quantum-gateway for the sake of this charm) is needed for each one. Each
gateway needs to be deployed as a seperate service so that the external
network id can be set differently for each gateway e.g.

    juju deploy quantum-gateway quantum-gateway-extnet1
    juju add-relation quantum-gateway-extnet1 mysql
    juju add-relation quantum-gateway-extnet1 rabbitmq-server
    juju add-relation quantum-gateway-extnet1 nova-cloud-controller
    juju deploy quantum-gateway quantum-gateway-extnet2
    juju add-relation quantum-gateway-extnet2 mysql
    juju add-relation quantum-gateway-extnet2 rabbitmq-server
    juju add-relation quantum-gateway-extnet2 nova-cloud-controller

    Create extnet1 and extnet2 via neutron client and take a note of their ids

    juju set quantum-gateway-extnet1 "run-internal-router=leader"
    juju set quantum-gateway-extnet2 "run-internal-router=none"
    juju set quantum-gateway-extnet1 "external-network-id=<extnet1 id>"
    juju set quantum-gateway-extnet2 "external-network-id=<extnet2 id>"

See upstream [Neutron multi extnet](http://docs.openstack.org/trunk/config-reference/content/adv_cfg_l3_agent_multi_extnet.html)

TODO
----

 * Provide more network configuration use cases.
 * Support VLAN in addition to GRE+OpenFlow for L2 separation.
