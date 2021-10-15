#!/bin/bash
# v2 functions for running with jenkins and
# the modern ECS/Fargate cluster implementation

send_teams() {
    TEXT=$(echo $1)
    # env var from config-secrets.sh
    WEBHOOK_URL=$TEAMS_WEBHOOK_URL
    MESSAGE=$( echo ${TEXT} | sed 's/"/\"/g' | sed "s/'/\'/g" )
    JSON="{\"text\": \"<pre>${MESSAGE}<\/pre>\" }"
    curl -H "Content-Type: application/json" -d "${JSON}" "${WEBHOOK_URL}" -s > /dev/null
}


get_prod_env() {
    # dig against AWS resolvers doesn't work in-office
    #prod_lb_cname=$(dig ais-prod.citygeo.phila.city +short | grep -o "blue\|green")

    # determine our prod env by checking what cnames are in our prod records in our hosted zone
    # and then grepping for either blue or green.
    # The hosted-zone-id is for our citygeo.phila.city hosted zone in AWS.
    prod_lb_color=$(aws route53 list-resource-record-sets \
                    --hosted-zone-id $PHILACITY_ZONE_ID \
                    --query "ResourceRecordSets[?Name == '$PROD_ENDPOINT.']" | grep -o "blue\|green"
    )

    # Return either blue or green string
    echo $prod_lb_color
}

