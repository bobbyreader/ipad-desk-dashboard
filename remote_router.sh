#!/bin/sh
# Read-only snapshot; executed via SSH stdin, never installed on the router.
set -eu
printf '__UPTIME__\n'
cat /proc/uptime
printf '__DEV__\n'
cat /proc/net/dev
printf '__CONNTRACK__\n'
cat /proc/net/nf_conntrack
printf '__LEASES__\n'
if [ -r /tmp/dhcp.leases ]; then cat /tmp/dhcp.leases; fi
printf '__OPTIONS__\n'
printf 'accounting='
cat /proc/sys/net/netfilter/nf_conntrack_acct
printf 'software_offload='
uci -q get firewall.@defaults[0].flow_offloading || true
printf '\nhardware_offload='
uci -q get firewall.@defaults[0].flow_offloading_hw || true
printf '\n__END__\n'
