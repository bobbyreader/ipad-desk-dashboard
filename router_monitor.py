"""Read-only side-router telemetry: physical counters and sampled per-device flows."""
from pathlib import Path
import subprocess
import threading
import time

from geo_places import PLACES
from proxy_monitor import ProxyMonitor, open_geoip_reader
from router_parser import parse_network, parse_snapshot
from settings import SETTINGS

ROOT = Path(__file__).resolve().parent


def region_bucket(regions: dict, code: str) -> dict:
    """Create an aggregate country bucket without retaining destination addresses."""
    name, lon, lat = PLACES[code]
    return regions.setdefault(code, {'code': code, 'name': name, 'lon': lon, 'lat': lat,
                                     'count': 0, 'bytes_per_sec': 0})


class RouterMonitor(ProxyMonitor):
    """Reuse offline geolocation and locked snapshot handling for a separate source."""

    def __init__(self, geoip_path: str | Path | None = None) -> None:
        """Initialize a separate router baseline and history."""
        configured_path = geoip_path or (SETTINGS.get('router') or {}).get('geoip_path', 'data/geoip.metadb')
        super().__init__(geoip_path=configured_path)
        self.reader = open_geoip_reader(configured_path)
        self.data = {'available': False, 'message': '正在连接旁路由', 'updated': None}

    def ingest(self, raw: dict, now: float, interface: str = 'eth0',
               aliases: dict | None = None, source_label: str = '') -> dict:
        """Difference only surviving counters; do not add interface and flow totals."""
        alias_map = aliases if aliases is not None else ((SETTINGS.get('router') or {}).get('aliases') or {})
        previous = self.previous
        elapsed = now - previous['time'] if previous else 0
        valid = bool(previous and 0 < elapsed < 20 and raw['uptime'] >= previous['uptime'])
        interfaces = {}
        for name, counters in raw['interfaces'].items():
            before = previous['interfaces'].get(name) if valid else None
            ok = bool(before and counters['rx'] >= before['rx'] and counters['tx'] >= before['tx'])
            interfaces[name] = dict(counters, rx_rate=(counters['rx']-before['rx'])/elapsed if ok else None,
                                    tx_rate=(counters['tx']-before['tx'])/elapsed if ok else None)
        old_flows = previous['flows'] if valid else {}
        devices, regions, current_flows = {}, {}, {}
        unknown = unassigned = ipv6 = public_count = internal = sampled = 0
        accounting = offloaded = 0
        for flow in raw['flows']:
            counters = flow['counters']
            current_flows[flow['key']] = counters
            accounting += counters is not None
            offloaded += flow['offloaded']
            ipv6 += flow['ipv6']
            device_ip = flow['device']
            if not device_ip:
                unassigned += 1
                continue
            device = devices.setdefault(device_ip, {
                'ip': device_ip, 'name': alias_map.get(device_ip, raw['leases'].get(device_ip, '局域网设备')),
                'connections': 0, 'send_rate': None, 'receive_rate': None,
                'sampled': 0, 'countries': {}, 'unknown': 0, 'public': 0, 'internal': 0,
            })
            device['connections'] += 1
            before = old_flows.get(flow['key'])
            delta = None
            if counters is not None and before is not None and all(a >= b for a, b in zip(counters, before)):
                delta = [(a-b)/elapsed for a, b in zip(counters, before)]
                if flow['reverse']:
                    delta.reverse()
                device['send_rate'] = (device['send_rate'] or 0) + delta[0]
                device['receive_rate'] = (device['receive_rate'] or 0) + delta[1]
                device['sampled'] += 1
                sampled += 1
            if flow['internal']:
                device['internal'] += 1
                internal += 1
            if not flow['public']:
                continue
            public_count += 1
            device['public'] += 1
            code = self.country({'ip': flow['remote']})
            if not code:
                device['unknown'] += 1
                unknown += 1
                continue
            for buckets in (regions, device['countries']):
                bucket = region_bucket(buckets, code)
                bucket['count'] += 1
                if delta:
                    bucket['bytes_per_sec'] += sum(delta)
        rows = []
        for device in devices.values():
            device['countries'] = list(device['countries'].values())
            rows.append(device)
        rows.sort(key=lambda d: (-(d['send_rate'] or 0)-(d['receive_rate'] or 0), -d['connections'], d['ip']))
        primary = interfaces.get(interface) or next(iter(interfaces.values()))
        self.history.append({'down': primary['rx_rate'], 'up': primary['tx_rate']})
        self.history = self.history[-60:]
        self.previous = {'time': now, 'uptime': raw['uptime'], 'interfaces': raw['interfaces'], 'flows': current_flows}
        return {
            'available': True, 'updated': time.time(), 'source': source_label,
            'interface': interface,
            'interfaces': interfaces, 'history': list(self.history), 'countries': list(regions.values()),
            'devices': rows, 'connections': raw['entries'], 'mapped_connections': public_count,
            'unknown': unknown, 'unassigned': unassigned, 'ipv6': ipv6, 'internal': internal,
            'sampled_connections': sampled, 'accounted_connections': accounting,
            'parse_errors': raw['parse_errors'], 'offloaded_connections': offloaded,
            'software_offload': raw['options'].get('software_offload') == '1',
            'hardware_offload': raw['options'].get('hardware_offload') == '1',
            'geo_available': self.reader is not None,
        }

    def poll(self) -> None:
        """Read existing kernel counters without installing or changing router services."""
        cfg = SETTINGS.get('router') or {}
        ssh_host = str(cfg.get('ssh_host') or '').strip()
        if not ssh_host:
            self.previous = None
            self.history = []
            with self.lock:
                self.data = {'available': False, 'message': '旁路由未配置（请设置 router.ssh_host）',
                             'updated': time.time()}
            return
        interface = str(cfg.get('interface') or 'eth0').strip() or 'eth0'
        lan_net = parse_network(cfg.get('lan_cidr'))
        aliases = cfg.get('aliases') or {}
        try:
            result = subprocess.run(
                ['ssh', '-C', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
                 '-o', 'StrictHostKeyChecking=yes', ssh_host, 'sh -s'],
                input=(ROOT / 'remote_router.sh').read_text(encoding='utf-8'), capture_output=True,
                text=True, timeout=8, check=True,
            )
            parsed = parse_snapshot(result.stdout, interface=interface, lan_network=lan_net)
            data = self.ingest(parsed, time.monotonic(), interface=interface,
                               aliases=aliases, source_label=ssh_host.split('@')[-1])
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, IndexError):
            self.previous = None
            self.history = []
            data = {'available': False, 'message': '旁路由采集暂不可用', 'updated': time.time()}
        with self.lock:
            self.data = data

    def snapshot(self) -> dict:
        """Return the cached result with a source-appropriate stale message."""
        data = super().snapshot()
        if data.get('message') == '代理数据已过期':
            data['message'] = '旁路由数据已过期'
        return data

    def run(self) -> None:
        """Collect at five-second intervals shared by all browser clients."""
        while True:
            started = time.monotonic()
            self.poll()
            time.sleep(max(0.2, 5 - (time.monotonic() - started)))

    def start(self) -> None:
        """Start the independent read-only router collector."""
        if self._started:
            return
        self._started = True
        threading.Thread(target=self.run, daemon=True, name='router-monitor').start()


router_monitor = RouterMonitor()
