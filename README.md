# 🔗 TonConnect CLI

> Headless TonConnect клиент для автоматической авторизации через `tc://` ссылки

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 Описание

**TonConnect CLI** — это headless-клиент для программной обработки TonConnect авторизаций. Позволяет автоматически подключаться к dApps через `tc://` ссылки без взаимодействия с UI кошелька.

### Основные возможности

✅ Полная поддержка TonConnect 2.0 протокола  
✅ Автоматическая генерация ton_proof для безопасной авторизации  
✅ Поддержка кошельков V4R2 и V5R1  
✅ Whitelist доменов для защиты от фишинга  
✅ Retry механизм для bridge запросов  
✅ Асинхронная архитектура с timeout управлением  
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
    result = await connect_tc_url(tc_url)
    
    if result.code == "DAPP_CONNECTED":
        print(f"✅ Подключено! ID: {result.data['id']}")
    else:
        print(f"❌ Ошибка: {result.error_message}")

asyncio.run(main())
```

## 📚 Документация

### Основные классы

#### TonConnectClient

Главный класс для работы с TonConnect.

```python
from TonConnect import TonConnectClient

client = TonConnectClient(
    mnemonic="your 24 words...",           # или через TON_WALLET_MNEMONIC
    bridge_url="https://bridge.tonapi.io/bridge",  # опционально
    connect_timeout=10,                     # таймаут подключения (сек)
    request_timeout=30                      # таймаут запросов (сек)
)

# Инициализация с whitelist доменов
await client.init(allowed_domains=["app.example.com", "dapp.io"])

# Подключение к dApp
result = await client.connect(tc_url)

# Закрытие соединений
await client.close()
```

### Результаты операций

#### TonConnectResult

```python
@dataclass
class TonConnectResult:
    code: TonConnectResultCode  # DAPP_CONNECTED | DAPP_CONNECTED_FAILED | FORBIDDEN
    data: Optional[dict]        # данные подключения
    error_code: Optional[TonConnectErrorCode]  # код ошибки
    error_message: Optional[str]  # описание ошибки
```

**Пример обработки:**

```python
result = await client.connect(tc_url)

match result.code:
    case "DAPP_CONNECTED":
        print(f"Успех! Event ID: {result.data['id']}")
        print(f"Время: {result.data['elapsed_ms']} ms")
    case "FORBIDDEN":
        print(f"Домен заблокирован: {result.error_message}")
    case "DAPP_CONNECTED_FAILED":
        print(f"Ошибка [{result.error_code}]: {result.error_message}")
```

## 💡 Примеры использования

### Пример 1: Интерактивный CLI

```python
import asyncio
import json
from TonConnect import TonConnectClient, TonConnectException

async def main():
    client = TonConnectClient()
    
    try:
        await client.init()
    except TonConnectException as e:
        print(f"❌ Ошибка инициализации: {e}")
        return
    
    try:
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
                "error_message": result.error_message
            }, indent=2))
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### Пример 2: Whitelist доменов

```python
async def secure_connect():
    client = TonConnectClient()
    
    # Разрешаем только проверенные домены
    await client.init(allowed_domains=[
        "app.dedust.io",
        "ston.fi",
        "app.evaa.finance"
    ])
    
    # Попытка подключения
    result = await client.connect(tc_url)
    
    if result.code == "FORBIDDEN":
        print(f"⛔ Домен заблокирован: {result.error_message}")
    
    await client.close()
```

## 🔒 Безопасность

### Хранение мнемоники

- **Никогда** не коммитьте `.env` файлы в репозиторий
- Используйте переменные окружения в production
- Мнемоника автоматически очищается из памяти после инициализации кошелька

### Whitelist доменов

```python
# Защита от фишинга
await client.init(allowed_domains=["trusted-app.com"])
```

## ⚙️ Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `TON_WALLET_MNEMONIC` | 24 слова seed phrase | ❌ Обязательно |
| `TON_WALLET_VERSION` | Версия кошелька: `v5r1` или `v4r2` | `v5r1` |

## 📄 Лицензия

Распространяется под MIT License. См. `LICENSE` для деталей.

## 🔗 Ссылки

**Автор:** [t.me/ripcats](https://t.me/ripcats)

- [TonAPI Bridge](https://tonapi.io/)
- [pytoniq](https://github.com/yungwine/pytoniq)

Вопросы? Открывайте [Issues](https://github.com/ripcats/ton-connect-cli/issues)
