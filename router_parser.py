"""Parse Linux conntrack snapshots without emitting raw public endpoints."""
import ipaddress
import re

DEFAULT_LAN = ipaddress.ip_network('192.168.1.0/24')


def parse_network(cidr: str | None) -> ipaddress.IPv4Network:
    """Parse configured IPv4 LAN CIDR, falling back to DEFAULT_LAN."""
    if cidr:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if isinstance(net, ipaddress.IPv4Network):
                return net
        except ValueError:
            pass
    return DEFAULT_LAN


def address(value: str):
    """Return a parsed address or None for malformed conntrack input."""
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def lan_ip(value: str, lan_network: ipaddress.IPv4Network = DEFAULT_LAN) -> bool:
    """Only attribute devices in the explicitly configured IPv4 LAN subnet."""
    ip = address(value)
    return bool(ip and ip.version == 4 and ip in lan_network)


def parse_flow(line: str, lan_network: ipaddress.IPv4Network = DEFAULT_LAN) -> dict | None:
    """Extract both tuples/counters, retaining identity across NAT and TCP states."""
    tokens = line.split()
    if len(tokens) < 5 or tokens[0] not in ('ipv4', 'ipv6'):
        return None
    fields = {}
    for key, value in re.findall(r'\b(\w+)=([^\s]+)', line):
        fields.setdefault(key, []).append(value)
    src, dst = fields.get('src', []), fields.get('dst', [])
    if len(src) != 2 or len(dst) != 2 or not all(address(ip) for ip in src + dst):
        return None
    counter = fields.get('bytes', [])
    try:
        counters = tuple(int(n) for n in counter) if len(counter) == 2 else None
        if counters and min(counters) < 0:
            return None
    except ValueError:
        return None
    identity = (tokens[0], tokens[2], tuple(src), tuple(dst),
                tuple(fields.get('sport', [])), tuple(fields.get('dport', [])),
                tuple(fields.get('type', [])), tuple(fields.get('code', [])),
                tuple(fields.get('id', [])), tuple(fields.get('zone', [])))
    device = None
    remote = None
    reverse = False
    if lan_ip(src[0], lan_network):
        device, remote = src[0], dst[0]
    elif address(src[0]).is_global and (lan_ip(dst[0], lan_network) or lan_ip(src[1], lan_network)):
        # Inbound or DNAT flow: the reply source identifies the local receiver.
        device = src[1] if lan_ip(src[1], lan_network) else dst[0]
        remote, reverse = src[0], True
    is_public = bool(remote and address(remote).is_global)
    return {'key': identity, 'device': device, 'remote': remote,
            'public': is_public, 'reverse': reverse, 'counters': counters,
            'ipv6': tokens[0] == 'ipv6', 'offloaded': 'OFFLOAD' in line,
            'internal': bool(device and remote and lan_ip(remote, lan_network))}


def parse_snapshot(output: str, interface: str = 'eth0',
                   lan_network: ipaddress.IPv4Network = DEFAULT_LAN) -> dict:
    """Parse allowlisted shell sections and require a complete remote snapshot."""
    names = ('UPTIME', 'DEV', 'CONNTRACK', 'LEASES', 'OPTIONS', 'END')
    sections = {}
    current = None
    seen = []
    for line in output.splitlines():
        if line.startswith('__') and line.endswith('__') and line[2:-2] in names:
            current = line[2:-2]
            seen.append(current)
            sections[current] = []
        elif current:
            sections[current].append(line)
    if seen != list(names):
        raise ValueError('Incomplete router snapshot')
    uptime = float(sections['UPTIME'][0].split()[0])
    interfaces = {}
    wanted = {interface, 'eth0', 'br-lan'}
    for line in sections['DEV']:
        if ':' not in line:
            continue
        name, values = line.split(':', 1)
        values = values.split()
        if name.strip() in wanted and len(values) >= 9:
            interfaces[name.strip()] = {'rx': int(values[0]), 'tx': int(values[8])}
    if interface not in interfaces:
        raise ValueError('Required interface missing')
    raw_flows = [line for line in sections['CONNTRACK'] if line.strip()]
    flows = [flow for line in raw_flows if (flow := parse_flow(line, lan_network)) is not None]
    leases = {}
    for line in sections['LEASES']:
        cols = line.split()
        if len(cols) >= 4 and lan_ip(cols[2], lan_network) and cols[3] != '*':
            leases[cols[2]] = cols[3][:80]
    options = dict(line.split('=', 1) for line in sections['OPTIONS'] if '=' in line)
    return {'uptime': uptime, 'interfaces': interfaces, 'flows': flows,
            'entries': len(raw_flows), 'parse_errors': len(raw_flows) - len(flows),
            'leases': leases, 'options': options}
