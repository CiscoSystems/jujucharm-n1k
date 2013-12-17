#!/bin/bash
SITE_CONF='/etc/apache2/sites-enabled/juju-gui'
ADDRESS='https://127.0.0.1:443/juju-ui/version.js'
LIFE_SIGN='jujuGuiVersionInfo'

if [[ ! -f $SITE_CONF ]]; then
    echo Apache is not configured serve juju-gui.
    exit 2
fi

match=$(curl -k $ADDRESS | grep "$LIFE_SIGN")

if [[ -z $match ]]; then
    echo juju-gui did not return content indicating it was loading.
    exit 2
fi
