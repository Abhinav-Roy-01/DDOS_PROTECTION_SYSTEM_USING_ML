# Deployment — Phase 1 checklist

This is the step-by-step deployment doc, filled in as Phase 1 is built.
Placeholder outline for now:

1. Provision VPS (Oracle Cloud free tier / DigitalOcean)
2. Point domain/subdomain DNS at the VPS IP
3. Install nginx, Redis, Python 3.11+, certbot
4. Clone this repo onto the VPS
5. Set up `.env` with real secrets (never commit this file)
6. `pip install -r API/requirements.txt`
7. Copy `INFRA/NGINX/NGINX.CONF.EXAMPLE` contents into
   `/etc/nginx/sites-available/ddos-shield` (lowercase), symlink to
   `sites-enabled`, `nginx -t`, reload
8. `certbot --nginx` for HTTPS
9. Copy systemd unit examples into `/etc/systemd/system/` (lowercase),
   `systemctl enable --now ddos-api`
10. Verify: `curl https://your-domain/health`

NOT YET FILLED IN with actual verified commands -- this happens as Phase
1 is built and tested for real.
