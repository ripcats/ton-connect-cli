# 🔗 TonConnect CLI

> Headless TonConnect клиент для автоматической авторизации через `tc://` ссылки

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.2.0-green.svg)](pyproject.toml)

## 📋 Описание

**TonConnect CLI** — headless-клиент для программной обработки TonConnect авторизаций. Позволяет автоматически подключаться к dApps через `tc://` ссылки без взаимодействия с UI кошелька.

### Основные возможности

✅ Полная поддержка TonConnect 2.0 протокола  
✅ Автоматическая генерация ton_proof для безопасной авторизации  
✅ Поддержка кошельков V4R2 и V5R1 через `WalletVersion` enum  
✅ Whitelist доменов для защиты от фишинга  
✅ Retry с экспоненциальным backoff для bridge запросов  
✅ Асинхронный context manager с автоматическим закрытием  
✅ Безопасная очистка мнемоник из памяти

## 🚀 Быстрый старт

### Установка

```bash
git clone https://github.com/ripcats/ton-connect-cli.git
cd ton-connect-cli
pip install .
```

### Настройка

Создайте `.env` файл с вашей мнемоникой:

```bash
TON_WALLET_MNEMONIC="your 24 words seed phrase here"
TON_WALLET_VERSION="v5r1"  # опционально: v5r1 (default) или v4r2
```

### Простейший пример

```python
import asyncio
from TonConnect import connect_tc_url

async def main():
    tc_url = "tc://connect?v=2&id=abc123&r=eyJ..."
    result = await connect_tc_url(
        tc_url,
        allowed_domains=["app.dedust.io", "ston.fi"],  # опционально
    )

    if result.ok:
        print(f"✅ Подключено за {result.data['elapsed_ms']} ms")
    else:
        print(f"❌ Ошибка: {result.error_message}")

asyncio.run(main())
```

## 📚 Документация

### TonConnectClient

Основной класс. Поддерживает два стиля использования.

**Context manager (рекомендуется):**

```python
from TonConnect import TonConnectClient

async with TonConnectClient(mnemonic="your 24 words...", allowed_domains=["app.dedust.io", "ston.fi"]) as client:
    result = await client.connect(tc_url)
```

**Ручное управление жизненным циклом:**

```python
client = TonConnectClient(mnemonic="your 24 words...")
await client.init()
result = await client.connect(tc_url)
await client.close()
```

#### Параметры конструктора

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `mnemonic` | `str \| None` | `TON_WALLET_MNEMONIC` из env | 24 слова seed phrase |
| `bridge_url` | `str \| None` | `bridge.tonapi.io` | TonConnect bridge URL |
| `wallet_version` | `WalletVersion \| None` | `TON_WALLET_VERSION` из env → V5R1 | Версия контракта кошелька |
| `connect_timeout` | `float \| None` | `10` | Таймаут инициализации кошелька (сек) |
| `request_timeout` | `float \| None` | `30` | Таймаут HTTP запросов (сек) |
| `retry_attempts` | `int` | `3` | Количество попыток отправки на bridge |
| `retry_base` | `float` | `0.5` | Базовая задержка backoff (сек) |
| `allowed_domains` | `list[str] \| None` | `None` (все домены) | Whitelist доменов. Можно изменить позже через свойство `allowed_domains` |

#### `init(allowed_domains=None)`

Инициализирует кошелёк и HTTP-сессию. При использовании context manager вызывается автоматически.

Если `allowed_domains` не передан (или `None`), уже установленный вайтлист (из конструктора или свойства) **сохраняется**. Явная передача списка переопределяет его.

```python
# задать домены при init()
await client.init(allowed_domains=["app.dedust.io", "ston.fi"])

# изменить вайтлист после инициализации
client.allowed_domains = ["ston.fi"]   # заменить целиком
client.allowed_domains = None          # отключить фильтрацию (все домены разрешены)
```

#### `connect(tc_url) → TonConnectResult`

Подключается к dApp по `tc://` ссылке. Бросает `TonConnectException` если URL невалиден. В остальных случаях возвращает `TonConnectResult`.

#### `close()`

Закрывает все соединения и освобождает ресурсы. При использовании context manager вызывается автоматически.

---

### WalletVersion

Enum для выбора версии контракта кошелька.

```python
from TonConnect.types import WalletVersion

async with TonConnectClient(wallet_version=WalletVersion.V4R2) as client:
    ...
```

| Значение | Описание |
|----------|----------|
| `WalletVersion.V5R1` | Wallet V5R1 (по умолчанию) |
| `WalletVersion.V4R2` | Wallet V4R2 |

---

### TonConnectResult

```python
@dataclass(frozen=True)
class TonConnectResult:
    code: TonConnectResultCode
    data: Optional[dict]
    error_code: Optional[TonConnectErrorCode]
    error_message: Optional[str]

    @property
    def ok(self) -> bool: ...
```

`result.ok` — быстрая проверка успеха вместо сравнения с enum.

**Коды результата:**

| `result.code` | Описание |
|---------------|----------|
| `DAPP_CONNECTED` | Подключение успешно |
| `FORBIDDEN` | Домен заблокирован whitelist'ом |
| `DAPP_CONNECTED_FAILED` | Ошибка подключения |

**Поля `result.data` при успехе:**

```python
{
    "id": int,          # timestamp события в ms
    "event": "connect",
    "elapsed_ms": int   # время выполнения
}
```

---

### connect_tc_url (хелпер)

Одноразовое подключение без ручного управления клиентом:

```python
from TonConnect import connect_tc_url
from TonConnect.types import WalletVersion

result = await connect_tc_url(
    tc_url="tc://...",
    mnemonic="your 24 words...",            # опционально
    wallet_version=WalletVersion.V5R1,      # опционально
    allowed_domains=["app.dedust.io"],      # опционально
)
```

---

## 💡 Примеры

### Интерактивный CLI

```python
import asyncio
import json
from TonConnect import TonConnectClient, TonConnectException

async def main():
    try:
        async with TonConnectClient() as client:
            while True:
                tc_url = input("TON Connect URL (exit для выхода): ").strip()
                if tc_url.lower() in {"exit", "quit"}:
                    break
                if not tc_url:
                    continue

                result = await client.connect(tc_url)
                print(json.dumps({
                    "code": result.code.value,
                    "data": result.data,
                    "error_code": result.error_code.value if result.error_code else None,
                    "error_message": result.error_message,
                }, indent=2))
    except TonConnectException as e:
        print(f"❌ Ошибка инициализации [{e.code}]: {e}")

asyncio.run(main())
```

### Whitelist доменов

```python
from TonConnect import TonConnectClient
from TonConnect.types import TonConnectResultCode

TRUSTED = ["app.dedust.io", "ston.fi", "app.evaa.finance"]

# вариант 1 — задать сразу в конструкторе (работает с context manager без init())
async with TonConnectClient(allowed_domains=TRUSTED) as client:
    result = await client.connect(tc_url)

    if result.code == TonConnectResultCode.FORBIDDEN:
        print(f"⛔ Домен заблокирован: {result.error_message}")
    elif result.ok:
        print(f"✅ Подключено за {result.data['elapsed_ms']} ms")

# вариант 2 — переиспользуемый клиент с динамическим вайтлистом
async with TonConnectClient(allowed_domains=TRUSTED) as client:
    result1 = await client.connect(tc_url_1)

    # расширить вайтлист
    client.allowed_domains = TRUSTED + ["new-dapp.io"]
    result2 = await client.connect(tc_url_2)

    # снять ограничения
    client.allowed_domains = None
    result3 = await client.connect(tc_url_3)
```

### Настройка retry и таймаутов

```python
async with TonConnectClient(
    connect_timeout=15,
    request_timeout=60,
    retry_attempts=5,
    retry_base=1.0,
) as client:
    result = await client.connect(tc_url)
```

### Явный выбор версии кошелька

```python
from TonConnect import TonConnectClient
from TonConnect.types import WalletVersion

async with TonConnectClient(wallet_version=WalletVersion.V4R2) as client:
    result = await client.connect(tc_url)
```

---

## 🔒 Безопасность

- **Никогда** не коммитьте `.env` файлы в репозиторий
- Используйте переменные окружения в production
- Мнемоника автоматически обнуляется в памяти после инициализации кошелька
- Используйте `allowed_domains` для защиты от фишинговых dApps

---

## ⚙️ Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `TON_WALLET_MNEMONIC` | 24 слова seed phrase | ❌ Обязательно |
| `TON_WALLET_VERSION` | Версия кошелька: `v5r1` или `v4r2` | `v5r1` |

---

## 📄 Лицензия

Распространяется под MIT License. См. `LICENSE` для деталей.

## 🔗 Ссылки

**Автор:** [t.me/ripcats](https://t.me/ripcats)

- [TonAPI Bridge](https://tonapi.io/)
- [pytoniq](https://github.com/yungwine/pytoniq)

Вопросы? Открывайте [Issues](https://github.com/ripcats/ton-connect-cli/issues)
