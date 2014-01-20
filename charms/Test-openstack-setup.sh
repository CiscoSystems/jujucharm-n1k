# Deploy services to juju's bootstrap node
# The following services will be running here:
# - mysql
# - rabbitmq-server
# - openstack-dashboard
#juju deploy --to=0 mysql
#juju deploy --to=0 rabbitmq-server

# Deploy the services that will require their
# own instance so we can speed up the process
# - keystone
# - nova-compute
# - quantum-gateway
juju deploy --config ./openstack.yaml keystone

juju deploy -u --config ./openstack.yaml --repository=. local:precise/nova-compute 
juju deploy -u --config ./openstack.yaml --repository=. local:precise/quantum-gateway
# Deploy services to the main cluster controller
# The following services will be running here:
# - nova-cloud-controller
juju deploy -u --config ./openstack.yaml --repository=. local:precise/nova-cloud-controller --to=1 

# Relate the services
juju add-relation keystone mysql
juju add-relation nova-cloud-controller mysql
juju add-relation nova-cloud-controller rabbitmq-server
juju add-relation nova-cloud-controller keystone
juju add-relation nova-compute mysql
juju add-relation nova-compute:amqp rabbitmq-server:amqp
juju add-relation nova-compute nova-cloud-controller
juju add-relation quantum-gateway mysql
juju add-relation quantum-gateway nova-cloud-controller
juju add-relation quantum-gateway rabbitmq-server

