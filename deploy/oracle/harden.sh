#!/usr/bin/env bash
# Defence in depth for DropDL Web: the container may reach the internet, but not the cloud provider's metadata service
# or any private network. The app already refuses such links; this makes the network enforce it too.
# Run on the server after `docker compose up -d`:   sudo bash harden.sh
set -euo pipefail

SUBNET="172.30.0.0/24"   # must match the subnet in docker-compose.yml

add() { iptables -C DOCKER-USER "$@" 2>/dev/null || iptables -I DOCKER-USER "$@"; }

# Insert order is reversed (each rule goes to the top): the ACCEPT for the app's own subnet ends up first.
for blocked in 169.254.0.0/16 10.0.0.0/8 192.168.0.0/16 100.64.0.0/10 172.16.0.0/12 127.0.0.0/8; do
  add -s "$SUBNET" -d "$blocked" -j DROP
done
add -s "$SUBNET" -d "$SUBNET" -j ACCEPT

echo "Rules added. Check them with:  sudo iptables -L DOCKER-USER -n --line-numbers"
echo "To keep them after a reboot:  sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save"
