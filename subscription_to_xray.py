#!/usr/bin/env python3
'''Download an Xray subscription and write a JSON client config per location.'''

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

USER_AGENT = 'v2rayN/6.55'
SUPPORTED_SCHEMES = ('vless', 'vmess', 'trojan', 'ss', 'hysteria2', 'hy2')
VLESS_TRANSPORTS = frozenset({'tcp', 'raw', 'ws', 'websocket', 'grpc', 'xhttp'})
STREAM_TRANSPORTS = frozenset({'tcp', 'raw', 'ws', 'websocket', 'grpc'})

INVALID_FILENAME = re.compile(r'[<>:"/\\|?*#\x00-\x1f]')
EMOJI = re.compile(
    r'[\U0001F1E6-\U0001F1FF]'  # regional indicator flags
    r'|[\U0001F300-\U0001FAFF]'  # other emoji
    r'|[\u2600-\u27BF]'  # dingbats / miscellaneous symbols (e.g. skull)
    r'|[\u200d\ufe0f\u20e3]'
)


@dataclass
class StreamParams:
    network: str = 'tcp'
    security: str = ''
    server_name: str = ''
    fingerprint: str = ''
    alpn: list[str] = field(default_factory=list)
    allow_insecure: bool = False
    public_key: str = ''
    short_id: str = ''
    spider_x: str = ''
    mldsa: str = ''
    host: str = ''
    path: str = ''
    mode: str = ''
    service_name: str = ''
    header_type: str = ''
    address: str = ''


def fetch_subscription(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/plain'})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='replace')


def decode_subscription(body: str) -> list[str]:
    body = body.strip()
    if not body:
        return []
    if '://' not in body:
        padded = body + '=' * ((4 - len(body) % 4) % 4)
        body = base64.b64decode(padded).decode('utf-8', errors='replace').strip()
    return [line.strip() for line in body.splitlines() if line.strip()]


def read_url_file(path: Path) -> str:
    try:
        text = path.expanduser().read_text(encoding='utf-8')
    except OSError as exc:
        raise SystemExit(f'Не удалось прочитать файл с URL: {exc}') from exc

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        return line
    raise SystemExit(f'В файле {path} нет URL')


def resolve_url(args: argparse.Namespace) -> str:
    if args.url_file is not None:
        return read_url_file(args.url_file)
    return args.url


def first(query: dict[str, list[str]], key: str, default: str = '') -> str:
    values = query.get(key)
    return values[0] if values else default


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


def as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def b64decode_flex(data: str) -> bytes:
    payload = ''.join(data.split())
    padded = payload + '=' * ((4 - len(payload) % 4) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(padded)
        except Exception:
            continue
    raise ValueError('не удалось декодировать base64')


def query_of(parsed) -> dict[str, list[str]]:
    return parse_qs(parsed.query)


def fragment_name(uri: str) -> str:
    if '#' not in uri:
        return ''
    return unquote(uri.rsplit('#', 1)[1].strip()).strip()


def location_name(*parts: str, index: int) -> str:
    for part in parts:
        if part:
            return part
    return f'location-{index:02d}'


def to_filename(name: str) -> str:
    slug = EMOJI.sub('', name)
    slug = INVALID_FILENAME.sub('', slug)
    slug = re.sub(r'\s+', '-', slug.strip())
    slug = slug.replace('[', '').replace(']', '')
    slug = re.sub(r'-{2,}', '-', slug).strip('.-')
    return slug or 'unnamed'


def unique_path(directory: Path, filename: str) -> Path:
    path = directory / f'{filename}.json'
    if not path.exists():
        return path
    for suffix in range(2, 1000):
        candidate = directory / f'{filename}-{suffix}.json'
        if not candidate.exists():
            return candidate
    raise RuntimeError(f'Не удалось подобрать имя для {filename}')


def normalize_network(network: str) -> str:
    if network == 'websocket':
        return 'ws'
    return network or 'tcp'


def validate_transport(protocol: str, network: str) -> None:
    allowed = VLESS_TRANSPORTS if protocol == 'vless' else STREAM_TRANSPORTS
    if network not in allowed:
        raise ValueError(f'неподдерживаемый транспорт для {protocol}: {network}')


def stream_from_query(
    parsed,
    *,
    default_network: str = 'tcp',
    default_security: str = '',
) -> StreamParams:
    query = query_of(parsed)
    network = normalize_network(first(query, 'type', default_network))
    security = first(query, 'security', default_security)
    grpc = network == 'grpc'
    return StreamParams(
        network=network,
        security=security,
        server_name=first(query, 'sni'),
        fingerprint=first(query, 'fp'),
        alpn=split_csv(first(query, 'alpn')),
        allow_insecure=first(query, 'allowInsecure') == '1' or first(query, 'insecure') == '1',
        public_key=first(query, 'pbk'),
        short_id=first(query, 'sid'),
        spider_x=first(query, 'spx'),
        mldsa=first(query, 'pqv'),
        host=first(query, 'host'),
        path=unquote(first(query, 'path')),
        mode=first(query, 'mode'),
        service_name=first(query, 'serviceName') or (first(query, 'path') if grpc else ''),
        header_type=first(query, 'headerType'),
        address=parsed.hostname or '',
    )


def build_stream_settings(sp: StreamParams) -> dict:
    network = normalize_network(sp.network)
    stream: dict = {'network': network}

    if sp.security == 'reality':
        stream['security'] = 'reality'
        reality: dict = {
            'show': False,
            'fingerprint': sp.fingerprint or 'chrome',
            'serverName': sp.server_name,
            'publicKey': sp.public_key,
        }
        if sp.short_id:
            reality['shortId'] = sp.short_id
        if sp.spider_x:
            reality['spiderX'] = sp.spider_x
        if sp.mldsa:
            reality['mldsa65Verify'] = sp.mldsa
        stream['realitySettings'] = reality
    elif sp.security == 'tls':
        stream['security'] = 'tls'
        tls: dict = {
            'allowInsecure': sp.allow_insecure,
            'serverName': sp.server_name or sp.address,
            'fingerprint': sp.fingerprint or 'chrome',
        }
        if sp.alpn:
            tls['alpn'] = sp.alpn
        stream['tlsSettings'] = tls
    elif sp.security and sp.security != 'none':
        stream['security'] = sp.security

    if network == 'ws':
        ws: dict = {}
        if sp.path:
            ws['path'] = sp.path
        if sp.host:
            ws['host'] = sp.host
            ws['headers'] = {'Host': sp.host}
        if ws:
            stream['wsSettings'] = ws
    elif network == 'grpc':
        grpc: dict = {}
        service_name = sp.service_name or sp.path
        if service_name:
            grpc['serviceName'] = service_name
        if sp.host:
            grpc['authority'] = sp.host
        if sp.mode.lower() == 'multi':
            grpc['multiMode'] = True
        if grpc:
            stream['grpcSettings'] = grpc
    elif network == 'xhttp':
        xhttp: dict = {}
        if sp.host:
            xhttp['host'] = sp.host
        if sp.path:
            xhttp['path'] = sp.path
        if sp.mode:
            xhttp['mode'] = sp.mode
        if xhttp:
            stream['xhttpSettings'] = xhttp
    elif network in {'tcp', 'raw'} and sp.header_type and sp.header_type != 'none':
        stream['tcpSettings'] = {'header': {'type': sp.header_type}}

    return stream


def tagged(outbound: dict) -> dict:
    outbound['tag'] = 'proxy'
    return outbound


def parse_vless(uri: str) -> tuple[dict, str]:
    parsed = urlparse(uri)
    uuid = unquote(parsed.username or '')
    host = parsed.hostname
    if not uuid or not host:
        raise ValueError('vless: нет UUID или адреса')

    stream = stream_from_query(parsed, default_network='tcp', default_security='none')
    validate_transport('vless', stream.network)
    query = query_of(parsed)
    user: dict = {
        'id': uuid,
        'encryption': first(query, 'encryption', 'none'),
    }
    flow = first(query, 'flow')
    if flow:
        user['flow'] = flow

    outbound = {
        'protocol': 'vless',
        'settings': {
            'vnext': [
                {
                    'address': host,
                    'port': parsed.port or 443,
                    'users': [user],
                }
            ]
        },
        'streamSettings': build_stream_settings(stream),
    }
    return tagged(outbound), location_name(fragment_name(uri), host, index=0)


def parse_vmess(uri: str) -> tuple[dict, str]:
    payload = uri[len('vmess://'):]
    remark = ''
    if '#' in payload:
        payload, remark = payload.split('#', 1)
        remark = unquote(remark.strip())
    data = json.loads(b64decode_flex(payload))
    address = str(data.get('add') or '').strip()
    user_id = str(data.get('id') or '').strip()
    if not address or not user_id:
        raise ValueError('vmess: нет адреса или UUID')

    network = normalize_network(str(data.get('net') or 'tcp'))
    validate_transport('vmess', network)
    tls = str(data.get('tls') or '')
    security = 'tls' if tls == 'tls' else ('reality' if tls == 'reality' else 'none')
    stream = StreamParams(
        network=network,
        security=security,
        server_name=str(data.get('sni') or ''),
        fingerprint=str(data.get('fp') or ''),
        alpn=split_csv(str(data.get('alpn') or '')),
        host=str(data.get('host') or ''),
        path=str(data.get('path') or ''),
        service_name=str(data.get('path') or ''),
        header_type=str(data.get('type') or ''),
        address=address,
        public_key=str(data.get('pbk') or ''),
        short_id=str(data.get('sid') or ''),
        spider_x=str(data.get('spx') or ''),
    )
    outbound = {
        'protocol': 'vmess',
        'settings': {
            'vnext': [
                {
                    'address': address,
                    'port': as_int(data.get('port'), 443),
                    'users': [
                        {
                            'id': user_id,
                            'alterId': as_int(data.get('aid'), 0),
                            'security': str(data.get('scy') or 'auto'),
                        }
                    ],
                }
            ]
        },
        'streamSettings': build_stream_settings(stream),
    }
    name = location_name(str(data.get('ps') or '').strip(), remark, address, index=0)
    return tagged(outbound), name


def parse_trojan(uri: str) -> tuple[dict, str]:
    parsed = urlparse(uri)
    password = unquote(parsed.username or '')
    host = parsed.hostname
    if not password or not host:
        raise ValueError('trojan: нет пароля или адреса')

    stream = stream_from_query(parsed, default_network='tcp', default_security='tls')
    validate_transport('trojan', stream.network)
    server: dict = {
        'address': host,
        'port': parsed.port or 443,
        'password': password,
    }
    flow = first(query_of(parsed), 'flow')
    if flow:
        server['flow'] = flow
    outbound = {
        'protocol': 'trojan',
        'settings': {'servers': [server]},
        'streamSettings': build_stream_settings(stream),
    }
    return tagged(outbound), location_name(fragment_name(uri), host, index=0)


def parse_ss(uri: str) -> tuple[dict, str]:
    parsed = urlparse(uri)
    host = parsed.hostname
    port = parsed.port or 443
    method = ''
    password = ''

    if parsed.username and host:
        if parsed.password is not None:
            method = unquote(parsed.username)
            password = unquote(parsed.password)
        else:
            userinfo = unquote(parsed.username)
            try:
                decoded = b64decode_flex(userinfo).decode('utf-8')
            except ValueError:
                decoded = userinfo
            if ':' not in decoded:
                raise ValueError('ss: неверный формат credentials')
            method, password = decoded.split(':', 1)
    else:
        payload = uri[len('ss://'):]
        if '#' in payload:
            payload = payload.split('#', 1)[0]
        decoded = b64decode_flex(payload).decode('utf-8')
        if '@' not in decoded or ':' not in decoded:
            raise ValueError('ss: неверный формат ссылки')
        userinfo, server = decoded.rsplit('@', 1)
        method, password = userinfo.split(':', 1)
        if ':' in server:
            host, port_s = server.rsplit(':', 1)
            port = as_int(port_s, 443)
        else:
            host = server

    if not method or not password or not host:
        raise ValueError('ss: нет метода, пароля или адреса')

    outbound = {
        'protocol': 'shadowsocks',
        'settings': {
            'servers': [
                {
                    'address': host,
                    'port': port,
                    'method': method,
                    'password': password,
                }
            ]
        },
    }
    return tagged(outbound), location_name(fragment_name(uri), host, index=0)


def parse_hysteria2(uri: str) -> tuple[dict, str]:
    parsed = urlparse(uri)
    host = parsed.hostname
    if not host:
        raise ValueError('hysteria2: нет адреса')
    query = query_of(parsed)
    auth = unquote(parsed.username or '') or first(query, 'auth') or first(query, 'password')
    sni = first(query, 'sni') or host
    insecure = first(query, 'insecure') == '1' or first(query, 'allowInsecure') == '1'
    outbound = {
        'protocol': 'hysteria',
        'settings': {
            'version': 2,
            'address': host,
            'port': parsed.port or 443,
        },
        'streamSettings': {
            'network': 'hysteria',
            'security': 'tls',
            'tlsSettings': {
                'serverName': sni,
                'allowInsecure': insecure,
            },
            'hysteriaSettings': {
                'version': 2,
                'auth': auth,
                'keepAlivePeriod': 5,
            },
        },
    }
    return tagged(outbound), location_name(fragment_name(uri), host, index=0)


PARSERS = {
    'vless': parse_vless,
    'vmess': parse_vmess,
    'trojan': parse_trojan,
    'ss': parse_ss,
    'hysteria2': parse_hysteria2,
    'hy2': parse_hysteria2,
}


def parse_proxy(uri: str) -> tuple[dict, str]:
    scheme = uri.split('://', 1)[0].lower()
    parser = PARSERS.get(scheme)
    if parser is None:
        supported = ', '.join(SUPPORTED_SCHEMES)
        raise ValueError(f'неподдерживаемая схема: {scheme} (доступны {supported})')
    return parser(uri)


def build_client_config(
    outbound: dict,
    *,
    socks_port: int,
    http_port: int,
    listen: str,
    log_level: str,
) -> dict:
    inbounds = [
        {
            'tag': 'socks',
            'listen': listen,
            'port': socks_port,
            'protocol': 'socks',
            'settings': {'udp': True, 'auth': 'noauth'},
            'sniffing': {
                'enabled': True,
                'destOverride': ['http', 'tls', 'quic'],
                'routeOnly': True,
            },
        }
    ]
    if http_port:
        inbounds.append(
            {
                'tag': 'http',
                'listen': listen,
                'port': http_port,
                'protocol': 'http',
                'sniffing': {
                    'enabled': True,
                    'destOverride': ['http', 'tls', 'quic'],
                    'routeOnly': True,
                },
            }
        )

    return {
        'log': {'loglevel': log_level},
        'inbounds': inbounds,
        'outbounds': [outbound],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Генерирует JSON-конфиги Xray по ссылке на подписку.'
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        '--url',
        help='URL подписки (попадает в историю shell)',
    )
    source.add_argument(
        '--url-file',
        type=Path,
        metavar='FILE',
        help='Файл с URL подписки (одна строка, строки с # игнорируются)',
    )
    parser.add_argument(
        '-o',
        '--output',
        default='./configs',
        help='Папка для JSON-файлов (по умолчанию ./configs)',
    )
    parser.add_argument('--listen', default='127.0.0.1', help='Адрес локальных inbound')
    parser.add_argument('--socks-port', type=int, default=10808)
    parser.add_argument('--http-port', type=int, default=10809, help='0 — не создавать HTTP inbound')
    parser.add_argument('--log-level', default='warning')
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Удалить старые .json в папке перед генерацией',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    url = resolve_url(args)
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.clean:
        for old in output_dir.glob('*.json'):
            old.unlink()

    try:
        body = fetch_subscription(url)
    except URLError as exc:
        print(f'Не удалось скачать подписку: {exc}', file=sys.stderr)
        return 1

    links = decode_subscription(body)
    if not links:
        print('Подписка пустая или не распознана.', file=sys.stderr)
        return 1

    written = 0
    skipped = 0
    for index, link in enumerate(links, start=1):
        try:
            outbound, name = parse_proxy(link)
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            print(f'Пропуск #{index}: {exc}')
            skipped += 1
            continue

        name = location_name(name, index=index)
        path = unique_path(output_dir, to_filename(name))
        config = build_client_config(
            outbound,
            socks_port=args.socks_port,
            http_port=args.http_port,
            listen=args.listen,
            log_level=args.log_level,
        )
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'{path.name}  ←  {name}')
        written += 1

    print(f'\nГотово: {written} конфигов в {output_dir}')
    if skipped:
        print(f'Пропущено: {skipped}')
    return 0 if written else 1


if __name__ == '__main__':
    raise SystemExit(main())
