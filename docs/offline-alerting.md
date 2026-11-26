# K12 offline alerting

Gatus and Alertmanager run on K12, so they cannot report K12 going down. The
Cloudflare **Tunnel health alert** covers that from outside: if K12 loses power
or internet, its tunnel connectors drop and Cloudflare sends an email.

## Setup

Cloudflare dashboard → Notifications → Create → Availability & performance →
**Tunnel health alert**:

- Tunnels: Monitor everything (includes non-K12 tunnels and any added later)
- Notify on: all
- Destination: email, the Cloudflare login address

## Not covered

If K12 and its tunnels stay up while Alertmanager or Gatus is broken, nothing
reports it. A dead-man's switch on the `Watchdog` alert (for example
healthchecks.io) would close that gap; it is not set up.

Delivery has not been tested with a real outage.
