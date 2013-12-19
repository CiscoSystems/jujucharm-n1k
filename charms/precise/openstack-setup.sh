# Deploy services to juju's bootstrap node
# The following services will be running here:
# - mysql
# - rabbitmq-server
# - openstack-dashboard
juju deploy --to=0 mysql
juju deploy --to=0 rabbitmq-server

# Deploy the services that will require their
# own instance so we can speed up the process
# - keystone
# - swift-proxy
# - swift-storage
# - ceph
# - nova-compute
# - quantum-gateway
juju deploy --config ./openstack.yaml keystone
juju deploy -u --config ./openstack.yaml --repository=. local:precise/swift-proxy
juju deploy -u --config ./openstack.yaml --repository=. local:precise/swift-storage

juju deploy --config ./openstack.yaml ceph
juju deploy -u --config ./openstack.yaml --repository=. local:precise/nova-compute -n 2
juju deploy -u --config ./openstack.yaml --repository=. local:precise/quantum-gateway
# Deploy services to the main cluster controller
# The following services will be running here:
# - cinder
# - nova-cloud-controller
# - glance
juju deploy -u --to=1 --config ./openstack.yaml --repository=. local:precise/cinder
juju deploy -u --config ./openstack.yaml --repository=. local:precise/nova-cloud-controller --to=1 
juju deploy -u --to=1 --config ./openstack.yaml --repository=. local:precise/glance
juju deploy --config ./openstack.yaml openstack-dashboard

# Relate the services
juju add-relation keystone mysql
juju add-relation nova-cloud-controller mysql
juju add-relation nova-cloud-controller rabbitmq-server
juju add-relation nova-cloud-controller glance
juju add-relation nova-cloud-controller keystone
juju add-relation nova-compute mysql
juju add-relation nova-compute:amqp rabbitmq-server:amqp
juju add-relation nova-compute glance
juju add-relation nova-compute nova-cloud-controller
juju add-relation glance mysql
juju add-relation glance keystone
juju add-relation openstack-dashboard keystone
juju add-relation swift-proxy keystone
juju add-relation swift-proxy swift-storage
juju add-relation cinder keystone
juju add-relation cinder mysql
juju add-relation cinder rabbitmq-server
juju add-relation cinder nova-cloud-controller
juju add-relation quantum-gateway mysql
juju add-relation quantum-gateway nova-cloud-controller
juju add-relation quantum-gateway rabbitmq-server
juju add-relation cinder ceph
juju add-relation glance ceph

# Expose openstack-dashboard
juju expose openstack-dashboard
