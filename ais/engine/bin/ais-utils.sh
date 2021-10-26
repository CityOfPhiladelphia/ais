#!/bin/bash
# v2 functions for running with jenkins and
# the modern ECS/Fargate cluster implementation

BLUE_CNAME='ais-blue-api-alb-880240193.us-east-1.elb.amazonaws.com'
GREEN_CNAME='ais-green-api-alb-887758562.us-east-1.elb.amazonaws.com'

BLUE_ENGINE_CNAME='ais-engine-blue.cfuoybzycpox.us-east-1.rds.amazonaws.com'
GREEN_ENGINE_CNAME='ais-engine-green.cfuoybzycpox.us-east-1.rds.amazonaws.com'


get_prod_env() {
    # dig against AWS resolvers doesn't work in-office
    #prod_lb_cname=$(dig ais-prod.citygeo.phila.city +short | grep -o "blue\|green")

    # determine our prod env by checking what cnames are in our prod records in our hosted zone
    # and then grepping for either blue or green.
    # The hosted-zone-id is for our citygeo.phila.city hosted zone in AWS.
    prod_lb_color=$(aws route53 list-resource-record-sets \
                    --hosted-zone-id Z05945981N60F9XLWFIBR \
                                --query "ResourceRecordSets[?Name == 'ais-prod.citygeo.phila.city.']" | grep -o "blue\|green"
    )

    # Return either blue or green string
    echo $prod_lb_color

}


swap_cnames() {
    # https://stackoverflow.com/a/14203146
    # accept one argument of -c for color of blue or green
    POSITIONAL=()
    while [[ $# -gt 0 ]]; do
      key="$1"

      case $key in
        -c|--color)
          COLOR="$2"
          shift # past argument
          shift # past value
          ;;
      esac
    done
    set -- "${POSITIONAL[@]}" # restore positional parameters
    if [[ "$COLOR" != "blue" ]] && [[ "$COLOR" != "green" ]]; then
        echo "Error, -c only accepts blue or green."
        return 1
    fi
    echo $COLOR
    if [[ "$COLOR" == "blue" ]]; then
        aws route53 change-resource-record-sets --hosted-zone-id Z05945981N60F9XLWFIBR --change-batch file://change-to-blue.json
    elif [[ "$COLOR" == "green" ]]; then
        aws route53 change-resource-record-sets --hosted-zone-id Z05945981N60F9XLWFIBR --change-batch file://change-to-green.json
    fi

}
