# xray-subscription-parser

[English](README.en.md)

Скрипт скачивает подписку Xray (список ссылок, обычный текст или Base64) и сохраняет отдельный JSON-конфиг клиента для каждой локации.

Нужен только Python 3.10+. Дополнительные пакеты не требуются.

## Установка

Из репозитория:

```bash
pip install git+https://github.com/antonlukyanov/xray-subscription-parser.git
```

Из локальной копии:

```bash
pip install .
```

После установки команда доступна в консоли:

```bash
xray-subscription-parser --url-file subscription.url -o ./configs
```

## Как пользоваться

Положите URL подписки в файл — так он не попадёт в историю shell:

```bash
echo 'https://example.com/subscription' > subscription.url
xray-subscription-parser --url-file subscription.url -o ./configs
```

Пустые строки и комментарии, начинающиеся с `#`, в файле игнорируются.

Либо передайте URL напрямую (он останется в истории команд):

```bash
xray-subscription-parser --url 'https://example.com/subscription' -o ./configs
```

Нужно указать `--url` или `--url-file`.

Без установки можно запустить файл напрямую:

```bash
python3 subscription_to_xray.py --url-file subscription.url -o ./configs
```

Запуск клиента:

```bash
xray run -c configs/example.json
```

По умолчанию локальные inbound:

- SOCKS5 — `127.0.0.1:10808`
- HTTP — `127.0.0.1:10809`

Весь трафик с этих портов уходит в выбранную локацию.

## Параметры

| Флаг | Описание |
| --- | --- |
| `--url` | URL подписки |
| `--url-file` | Файл с URL подписки |
| `-o`, `--output` | Папка для JSON-файлов (`./configs`) |
| `--listen` | Адрес inbound (`127.0.0.1`) |
| `--socks-port` | Порт SOCKS (`10808`) |
| `--http-port` | Порт HTTP (`10809`); `0` — не создавать HTTP inbound |
| `--log-level` | Уровень лога Xray (`warning`) |
| `--clean` | Удалить старые `.json` в папке перед генерацией |

`--url` и `--url-file` взаимоисключающие: нужен ровно один из них.

## Что поддерживается

- `vless` — REALITY / TLS / none; транспорты `tcp`, `raw`, `ws`, `grpc`, `xhttp`
- `vmess` — формат `vmess://base64(JSON)`
- `trojan`
- `shadowsocks` (`ss`)
- `hysteria2` / `hy2`

Для `vmess` и `trojan` транспорты: `tcp`, `raw`, `ws`, `grpc`. Узел с неизвестной схемой или удалённым транспортом пропускается с предупреждением, остальные конфиги всё равно создаются.

Имена файлов берутся из названия локации в ссылке. Эмодзи и небезопасные символы вырезаются.

## Лицензия

[MIT](LICENSE)
