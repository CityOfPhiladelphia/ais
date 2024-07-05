#!/usr/bin/env bash

send_teams() {
    TEXT=$(echo $1)
    WEBHOOK_URL='https://phila.webhook.office.com/webhookb2/763c9a83-0f38-4eb2-abfc-e0f2f41b6fbb@2046864f-68ea-497d-af34-a6629a6cd700/IncomingWebhook/d23e1f5b3aa54380843d2e7ab54dd689/99fdd4e1-23b3-4f5d-8398-06a885e26925'
    MESSAGE=$( echo ${TEXT} | sed 's/"/\"/g' | sed "s/'/\'/g" )
    JSON="{\"text\": \"<pre>${MESSAGE}<\/pre>\" }"
    curl -H "Content-Type: application/json" -d "${JSON}" "${WEBHOOK_URL}"
}
