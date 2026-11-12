"""Tests for NAT attribution, counter sampling and router failure boundaries."""
import ipaddress
import json
import subprocess
import unittest
from unittest.mock import patch

from router_monitor import RouterMonitor
from router_parser import parse_flow, parse_network, parse_snapshot
from settings import SETTINGS

LAN = ipaddress.ip_network('192.168.1.0/24')


def flow(src='192.168.1.11', dst='8.8.8.8', sent=100, received=200,
         reply_src=None, reply_dst=None, family='ipv4', sport=50000):
    return (f'{family} 2 tcp 6 431999 ESTABLISHED src={src} dst={dst} '
            f'sport={sport} dport=443 packets=1 bytes={sent} '
            f'src={reply_src or dst} dst={reply_dst or src} sport=443 dport={sport} '
            f'packets=2 bytes={received} [ASSURED] mark=0 zone=0 use=2')


def snapshot(lines, rx=1000, tx=2000, uptime=100):
    return parse_snapshot(
        f'__UPTIME__\n{uptime}.00 1000.00\n__DEV__\n'
        f'eth0: {rx} 1 0 0 0 0 0 0 {tx} 1 0 0 0 0 0 0\n'
        '__CONNTRACK__\n' + '\n'.join(lines) + '\n__LEASES__\n'
        '0 aa:bb:cc:dd:ee:ff 192.168.1.110 reader *\n'
        '__OPTIONS__\naccounting=1\nsoftware_offload=1\nhardware_offload=1\n__END__\n',
        interface='eth0', lan_network=LAN)


class ParserTests(unittest.TestCase):
    def test_parse_network_custom_and_fallback(self):
        self.assertEqual(str(parse_network('10.0.0.0/24')), '10.0.0.0/24')
        self.assertEqual(str(parse_network('not-a-cidr')), '192.168.1.0/24')

    def test_snat(self):
        data = parse_flow(flow(reply_dst='203.0.113.8'), lan_network=LAN)
        self.assertEqual(data['device'], '192.168.1.11')
        self.assertFalse(data['reverse'])

    def test_dnat(self):
        data = parse_flow(flow(src='8.8.8.8', dst='203.0.113.8',
                               reply_src='192.168.1.110', reply_dst='8.8.8.8'), lan_network=LAN)
        self.assertEqual(data['device'], '192.168.1.110')
        self.assertEqual(data['remote'], '8.8.8.8')
        self.assertTrue(data['reverse'])

    def test_no_counters_and_invalid_records(self):
        line = flow().replace('bytes=100', '').replace('bytes=200', '')
        self.assertIsNone(parse_flow(line, lan_network=LAN)['counters'])
        self.assertIsNone(parse_flow('broken record', lan_network=LAN))
        self.assertIsNone(parse_flow(flow(src='invalid'), lan_network=LAN))
        raw = snapshot([line, 'broken record'])
        self.assertEqual(raw['parse_errors'], 1)

    def test_incomplete_snapshot(self):
        with self.assertRaises(ValueError):
            parse_snapshot('__UPTIME__\n12 12\n__DEV__\n')


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.monitor = RouterMonitor()
        if self.monitor.reader:
            self.monitor.reader.close()
        self.monitor.reader = None
        self.monitor.country = lambda row: 'US' if row.get('ip') == '8.8.8.8' else ''

    def test_rates_and_totals_not_combined(self):
        first = self.monitor.ingest(snapshot([flow()]), 10, aliases={})
        self.assertIsNone(first['devices'][0]['receive_rate'])
        second = self.monitor.ingest(snapshot([flow(sent=200, received=500)], rx=1100, tx=2050), 15, aliases={})
        self.assertEqual(second['interfaces']['eth0']['rx_rate'], 20)
        self.assertEqual(second['devices'][0]['send_rate'], 20)
        self.assertEqual(second['devices'][0]['receive_rate'], 60)
        self.assertEqual(second['countries'][0]['bytes_per_sec'], 80)
        self.assertNotIn('8.8.8.8', json.dumps(second))
        self.assertNotIn('50000', json.dumps(second))

    def test_inbound_direction(self):
        args = dict(src='8.8.8.8', dst='203.0.113.8', reply_src='192.168.1.110', reply_dst='8.8.8.8')
        self.monitor.ingest(snapshot([flow(**args)]), 10, aliases={})
        result = self.monitor.ingest(snapshot([flow(**args, sent=400, received=250)]), 15, aliases={})
        self.assertEqual(result['devices'][0]['receive_rate'], 60)
        self.assertEqual(result['devices'][0]['send_rate'], 10)
        self.assertEqual(result['devices'][0]['name'], 'reader')

    def test_new_disappeared_and_reset_flows(self):
        self.monitor.ingest(snapshot([flow()]), 10, aliases={})
        result = self.monitor.ingest(snapshot([flow(sent=999999, sport=50001)]), 15, aliases={})
        self.assertIsNone(result['devices'][0]['send_rate'])
        reset = self.monitor.ingest(snapshot([flow(sent=10, sport=50001)]), 20, aliases={})
        self.assertIsNone(reset['devices'][0]['send_rate'])
        empty = self.monitor.ingest(snapshot([]), 25, aliases={})
        self.assertEqual(empty['devices'], [])
        self.assertEqual(empty['countries'], [])

    def test_reboot_and_interface_reset(self):
        self.monitor.ingest(snapshot([flow()], uptime=100), 10, aliases={})
        result = self.monitor.ingest(snapshot([flow(sent=300)], uptime=2), 15, aliases={})
        self.assertIsNone(result['interfaces']['eth0']['rx_rate'])
        self.assertIsNone(result['devices'][0]['send_rate'])
        result = self.monitor.ingest(snapshot([flow(sent=400)], rx=1, tx=1, uptime=7), 20, aliases={})
        self.assertIsNone(result['interfaces']['eth0']['rx_rate'])
        self.assertEqual(result['devices'][0]['send_rate'], 20)

    def test_internal_ipv6_and_unknown_country(self):
        lines = [flow(dst='192.168.1.247'), flow(src='2001:4860::1', dst='2606:4700::1', family='ipv6'),
                 flow(src='192.168.1.110', dst='1.1.1.1')]
        result = self.monitor.ingest(snapshot(lines), 10, aliases={})
        self.assertEqual(result['internal'], 1)
        self.assertEqual(result['ipv6'], 1)
        self.assertEqual(result['unassigned'], 1)
        self.assertEqual(result['unknown'], 1)
        self.assertEqual(result['countries'], [])
        self.assertEqual(len(result['devices']), 2)

    def test_unconfigured_router(self):
        with patch.dict(SETTINGS['router'], {'ssh_host': ''}):
            self.monitor.poll()
        self.assertFalse(self.monitor.snapshot()['available'])
        self.assertIn('未配置', self.monitor.snapshot()['message'])

    @patch('router_monitor.subprocess.run', side_effect=subprocess.TimeoutExpired('ssh', 8))
    def test_failure_recovery(self, run):
        self.monitor.ingest(snapshot([flow()]), 10, aliases={})
        with patch.dict(SETTINGS['router'], {'ssh_host': 'root@192.168.1.2'}):
            self.monitor.poll()
        self.assertFalse(self.monitor.snapshot()['available'])
        self.assertEqual(self.monitor.history, [])
        self.assertIsNone(self.monitor.ingest(snapshot([flow(sent=100000)]), 15, aliases={})['devices'][0]['send_rate'])


if __name__ == '__main__':
    unittest.main()
