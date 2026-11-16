# DropDL Web on Oracle Cloud "Always Free" (or any small Linux server)

Oracle's [Always Free](https://docs.oracle.com/iaas/Content/FreeTier/resourceref.htm) tier includes an Ampere A1 virtual machine, enough for this service. Sign-up asks for a payment card for identity; Always Free resources are not charged, but check Oracle's current terms, and note Oracle may reclaim instances that stay idle. These files were written from the platforms' documentation and have not been run on a live account yet.

## 1. Create the server

1. Create an Always Free **VM.Standard.A1.Flex** instance with Ubuntu 24.04 (2 cores and 12 GB is plenty).
2. In the instance's network security list allow inbound **TCP 80 and 443** (and 22 for you).
3. Point a name at the server's public IP. A free one: [duckdns.org](https://www.duckdns.org).

## 2. Install and start

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
git clone https://github.com/HamedGhaithan/DropDL.git && cd DropDL/deploy/oracle
cp .env.example .env && nano .env              # set DOMAIN (and optionally ABUSE_CONTACT)
docker compose up -d --build
```

Caddy gets a free HTTPS certificate for `DOMAIN` automatically (ports 80 and 443 must be reachable).

## 3. Lock down what the container can reach

```bash
sudo bash harden.sh
```

This blocks the container from the cloud provider's metadata service (`169.254.0.0/16`) and every private network, so even a bug in the link checks could not be used to read your instance's credentials. To keep the rules after a reboot: `sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save`.

## 4. Check it

```bash
python3 ../../web/smoke.py https://YOUR-DOMAIN --download
```

`TRUSTED_PROXY_HOPS` is already `1` here because Caddy is the only proxy. To confirm, add `DEBUG_CLIENT_IP: "1"` under `web.environment`, run `docker compose up -d`, open `https://YOUR-DOMAIN/api/whoami` (`detected` must be your public address), then remove it again.

## Updating

```bash
cd DropDL && git pull && cd deploy/oracle && docker compose up -d --build
```

yt-dlp updates itself every 12 hours inside the running container; rebuild only for changes to DropDL Web.
