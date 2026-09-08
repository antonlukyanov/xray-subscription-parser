# xray-subscription-parser

[Русский](README.md)

A script that downloads an Xray subscription (plain-text or Base64 share links) and writes a separate client JSON config for each location.

Python 3.10+ only. No extra packages.

## Install

From the repository:

```bash
pip install git+https://github.com/antonlukyanov/xray-subscription-parser.git
```

From a local checkout:

```bash
pip install .
```

After install, run it from the console:

```bash
xray-subscription-parser --url-file subscription.url -o ./configs
```

## Usage

Put the subscription URL in a file so it does not end up in shell history:

```bash
echo 'https://example.com/subscription' > subscription.url
xray-subscription-parser --url-file subscription.url -o ./configs
```

Empty lines and comments starting with `#` are ignored.

Or pass the URL on the command line (it will be stored in shell history):

```bash
xray-subscription-parser --url 'https://example.com/subscription' -o ./configs
```

Either `--url` or `--url-file` is required.

Without installing, you can still run the file directly:

```bash
python3 subscription_to_xray.py --url-file subscription.url -o ./configs
```

Run a client:

```bash
xray run -c configs/example.json
```

Default local inbounds:

- SOCKS5 — `127.0.0.1:10808`
- HTTP — `127.0.0.1:10809`

All traffic on these ports goes through the selected location.

## Options

| Flag | Description |
| --- | --- |
| `--url` | Subscription URL |
| `--url-file` | File containing the subscription URL |
| `-o`, `--output` | Output directory for JSON files (`./configs`) |
| `--listen` | Inbound listen address (`127.0.0.1`) |
| `--socks-port` | SOCKS port (`10808`) |
| `--http-port` | HTTP port (`10809`); `0` skips the HTTP inbound |
| `--log-level` | Xray log level (`warning`) |
| `--clean` | Delete old `.json` files in the output directory first |

`--url` and `--url-file` are mutually exclusive; exactly one is required.

## Supported protocols

- `vless` — REALITY / TLS / none; transports `tcp`, `raw`, `ws`, `grpc`, `xhttp`
- `vmess` — `vmess://base64(JSON)`
- `trojan`
- `shadowsocks` (`ss`)
- `hysteria2` / `hy2`

For `vmess` and `trojan`, transports are `tcp`, `raw`, `ws`, and `grpc`. A node with an unknown scheme or a removed transport is skipped with a warning; the rest of the configs are still written.

Filenames come from the location name in the share link. Emoji and unsafe characters are stripped.

## License

[MIT](LICENSE)
