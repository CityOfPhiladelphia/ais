#!/usr/bin/env bash


function generate_nginx_config() {
cat <<EOF
server {
    listen  [::]:80;
    return  301 https://\$host\$request_uri;
}

server {
    listen              443 ssl;
    ssl_certificate     $SSL_CERTIFICATE;
    ssl_certificate_key $SSL_CERTIFICATE_KEY;

    location / {
        proxy_pass_header Server;
        proxy_redirect off;

        proxy_set_header   Host              \$host;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;

        proxy_pass http://${INTERNAL_IP:-127.0.0.1}:${PORT:-5000};
    }

    location /static/ {
        autoindex on;
        alias $SRV_ROOT/static/;
    }
}
EOF
} # generate_nginx_config



function generate_nginx_config_nossl() {
cat <<EOF
server {
    listen  [::]:80;

    location / {
        proxy_pass_header Server;
        proxy_redirect off;

        proxy_set_header   Host              \$host;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;

        proxy_pass http://${INTERNAL_IP:-127.0.0.1}:${PORT:-5000};
    }

    location /static/ {
        autoindex on;
        alias $SRV_ROOT/static/;
    }
}
EOF
} # generate_nginx_config
