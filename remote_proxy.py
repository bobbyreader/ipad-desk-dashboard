"""Executed over SSH stdin or imported locally; keep the Mihomo secret on its host."""
import json
from pathlib import Path
import re
import shlex
import urllib.request

CONFIG_PATH = globals().get('CONFIG_PATH', '/opt/1panel/apps/mihomo/mihomo/config.yaml')
API_URL = globals().get('API_URL', 'http://127.0.0.1:9090/connections')


def collect(config_path: str | None = None, api_url: str | None = None) -> dict:
    """Read the loopback API and return only counters and geolocation inputs."""
    raw = Path(config_path or CONFIG_PATH).read_text(encoding='utf-8')
    match = re.search(r'^secret:\s*(.*)$', raw, re.M)
    parts = shlex.split(match.group(1), comments=True) if match else []
    secret = parts[0] if parts else ''
    headers = {'Authorization': 'Bearer ' + secret} if secret else {}
    request = urllib.request.Request(api_url or API_URL, headers=headers)
    with urllib.request.urlopen(request, timeout=3) as response:
        data = json.load(response)
    return {
        'download': data['downloadTotal'], 'upload': data['uploadTotal'],
        'connections': [{
            'id': row['id'],
            'ip': row.get('metadata', {}).get('destinationIP', ''),
            'geo': row.get('metadata', {}).get('destinationGeoIP') or [],
            'direct': 'DIRECT' in row.get('chains', []),
            'bytes': row.get('download', 0) + row.get('upload', 0),
        } for row in data.get('connections', [])],
    }


if __name__ == '__main__':
    try:
        print(json.dumps(collect()))
    except Exception:
        # Never send configuration values, URLs or authentication headers in errors.
        print(json.dumps({'error': 'Mihomo API unavailable'}))
        raise SystemExit(1)
