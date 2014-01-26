#!/bin/bash

LOG_TERMINAL=0
export LOG_TERMINAL

function logger () {
    if [ $LOG_TERMINAL -eq 1 ]
    then
        echo $1
    else
        juju-log $1
    fi
}

export -f logger
