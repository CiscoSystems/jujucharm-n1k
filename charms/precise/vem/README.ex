Overview
--------
VEM charm installs the Nexus 1000v virtual switch onto the 
compute/network nodes.

VEM charm is designed as a subordinate charm. The aim is to
have this charm installed on the nova-compute and the 
quantum-gateway hosts.


Usage
-----
In order to use Cisco Openstack solution we would need to 
install VEM on the nova-compute and quantum-gateway hosts. 
We need to have nova-compute deployed first and we would
have vem charm as subordinate it.

In the config.yaml you can provide general config that will
be common to all VEM hosts in environement. If you need to 
configure host-specific config to each host depending on its fqdn,
a mapping file can be provided as a string to the variable called
mapping.

juju deploy nova-compute
juju deploy --config=config.yaml vem
juju add-relation nova-compute vem
juju set vem mapping="$(cat mapping.yaml)"

Here is a sample of the mapping file:
maas-node-1:
  host_mgmt_intf: eth1
  uplink_profile: phys eth1 profile sys-uplink
  node-type: compute
maas-node-3:
  host_mgmt_intf: eth0
  uplink_profile: phys eth0 profile sys-uplink 
  node-type: network
  vtep_config: 'virt vmknic-int1 profile profint mode dhcp mac 00:21:32:43:54:76'
  
In this way, the hosts in the mapping mentioned in the mapping file will
get these specific config which will overwrite the generate config provided
in the config.yaml

In this release, the VEM charm wont support add-relation with the VSM charm.

Configuration
-------------


Contact Information
-------------------

Author:
Report bugs at: http://bugs.launchpad.net/charms/+source/charmname
Location: http://jujucharms.com/charms/distro/charmname


