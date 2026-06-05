import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import json
import os
from datetime import time

# Токен бота
TOKEN = "8365170231:AAHM2Z0V0kgR_QDiFqegwb0fC_dSHAd5r2o"

# Файл для хранения балансов
DATA_FILE = "balances.json"
LIMITS_FILE = "default_limits.json"

# Начальные лимиты (для сброса каждого 1-го числа)
DEFAULT_LIMITS = {
    "Кристина": {
        "Приват": 350000,
        "Пумб": 100000,
        "Райф": 146000,
    },
    "Артём": {
        "Приват": 395000,
        "Моно": 364000,
        "Пумб": 150000,
    }
}

# Начальные данные
DEFAULT_DATA = {
    "Кристина": {
        "Приват": {"баланс": 69000, "лимит": 350000},
        "Пумб": {"баланс": 17100, "лимит": 100000},
        "Райф": {"баланс": 119840, "лимит": 146000},
    },
    "Артём": {
        "Приват": {"баланс": 111749, "лимит": 395000},
        "Моно": {"баланс": 131431, "лимит": 364000},
        "Пумб": {"баланс": 982, "лимит": 150000},
    }
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    save_data(DEFAULT_DATA.copy())
    return DEFAULT_DATA.copy()

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_limits():
    if os.path.exists(LIMITS_FILE):
        with open(LIMITS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    save_limits(DEFAULT_LIMITS.copy())
    return DEFAULT_LIMITS.copy()

def save_limits(limits):
    with open(LIMITS_FILE, "w", encoding="utf-8") as f:
        json.dump(limits, f, ensure_ascii=False, indent=2)

def format_number(n):
    return f"{int(n):,}".replace(",", " ")

def get_balance_text(data):
    limits = load_limits()
    text = "💰 *Текущие балансы:*\n\n"
    for person, banks in data.items():
        text += f"👤 *{person}:*\n"
        for bank, info in banks.items():
            bal = info["баланс"]
            lim = info["лимит"]
            default_lim = limits.get(person, {}).get(bank, lim)
            used_pct = int(((default_lim - lim) / default_lim) * 100) if default_lim > 0 else 0
            bar = "🟢" if used_pct < 70 else "🟡" if used_pct < 90 else "🔴"
            text += f"  {bar} {bank}: `{format_number(bal)}` грн (лимит остаток {format_number(lim)}, {used_pct}% использовано)\n"
        text += "\n"
    return text

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    text = get_balance_text(data)
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    data = load_data()

    pattern = r'([+-]?\d+)\s+([\wа-яёА-ЯЁ]+)\s+([\wа-яёА-ЯЁ]+)|' \
              r'([\wа-яёА-ЯЁ]+)\s+([\wа-яёА-ЯЁ]+)\s+([+-]?\d+)'

    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return

    if match.group(1):
        amount_str = match.group(1)
        word1 = match.group(2)
        word2 = match.group(3)
    else:
        word1 = match.group(4)
        word2 = match.group(5)
        amount_str = match.group(6)

    amount = int(amount_str)

    persons = list(data.keys())
    banks_all = []
    for p in persons:
        banks_all.extend(data[p].keys())
    banks_all = list(set(banks_all))

    found_person = None
    found_bank = None

    for w in [word1, word2]:
        for person in persons:
            if person.lower() == w.lower():
                found_person = person
        for bank in banks_all:
            if bank.lower() == w.lower():
                found_bank = bank

    if not found_person or not found_bank:
        return

    if found_bank not in data.get(found_person, {}):
        await update.message.reply_text(f"❌ У {found_person} нет банка {found_bank}!")
        return

    old_bal = data[found_person][found_bank]["баланс"]
    old_lim = data[found_person][found_bank]["лимит"]

    new_bal = old_bal + amount

    if amount < 0:
        new_lim = max(0, old_lim + amount)
    else:
        new_lim = old_lim

    data[found_person][found_bank]["баланс"] = new_bal
    data[found_person][found_bank]["лимит"] = new_lim
    save_data(data)

    limits = load_limits()
    default_lim = limits.get(found_person, {}).get(found_bank, old_lim)
    used_pct = int(((default_lim - new_lim) / default_lim) * 100) if default_lim > 0 else 0
    sign = "+" if amount >= 0 else ""
    bar = "🟢" if used_pct < 70 else "🟡" if used_pct < 90 else "🔴"

    if amount < 0:
        lim_line = f"📉 Лимит: `{format_number(old_lim)}` → `{format_number(new_lim)}` грн\n"
    else:
        lim_line = f"📊 Лимит остаток: `{format_number(new_lim)}` грн\n"

    await update.message.reply_text(
        f"✅ *Обновлено!*\n"
        f"👤 {found_person} — {found_bank}\n"
        f"Было: `{format_number(old_bal)}` грн\n"
        f"Изменение: `{sign}{format_number(amount)}` грн\n"
        f"Стало: `{format_number(new_bal)}` грн\n"
        f"{lim_line}"
        f"{bar} Использовано лимита: {used_pct}%",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Команды бота:*\n\n"
        "/balance — показать все балансы\n"
        "/help — эта справка\n"
        "/set Имя Банк Сумма — установить точный баланс\n"
        "/setlimit Имя Банк Сумма — установить лимит (и сброс 1-го числа)\n\n"
        "*Как обновить баланс:*\n"
        "➕ Пополнение (только баланс):\n"
        "`+5000 Приват Кристина`\n\n"
        "➖ Списание (баланс и лимит):\n"
        "`-5596 Приват Кристина`\n\n"
        "🔄 Лимит сбрасывается 1-го числа каждого месяца"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "Формат: `/set Имя Банк Сумма`\n"
            "Пример: `/set Кристина Приват 75000`",
            parse_mode="Markdown"
        )
        return

    data = load_data()
    person, bank, amount_str = args[0], args[1], args[2]
    amount = int(amount_str)

    if person not in data:
        await update.message.reply_text(f"❌ Не знаю такого имени: {person}")
        return
    if bank not in data[person]:
        await update.message.reply_text(f"❌ У {person} нет банка {bank}")
        return

    old_bal = data[person][bank]["баланс"]
    data[person][bank]["баланс"] = amount
    save_data(data)

    await update.message.reply_text(
        f"✅ Баланс установлен!\n"
        f"👤 {person} — {bank}\n"
        f"Было: `{format_number(old_bal)}` грн\n"
        f"Стало: `{format_number(amount)}` грн",
        parse_mode="Markdown"
    )

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить лимит: /setlimit Кристина Приват 400000"""
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "Формат: `/setlimit Имя Банк Сумма`\n"
            "Пример: `/setlimit Кристина Приват 400000`",
            parse_mode="Markdown"
        )
        return

    data = load_data()
    limits = load_limits()
    person, bank, amount_str = args[0], args[1], args[2]
    amount = int(amount_str)

    if person not in data:
        await update.message.reply_text(f"❌ Не знаю такого имени: {person}")
        return
    if bank not in data[person]:
        await update.message.reply_text(f"❌ У {person} нет банка {bank}")
        return

    old_lim = limits.get(person, {}).get(bank, 0)

    # Обновляем лимит в текущих данных и в дефолтных
    data[person][bank]["лимит"] = amount
    if person not in limits:
        limits[person] = {}
    limits[person][bank] = amount

    save_data(data)
    save_limits(limits)

    await update.message.reply_text(
        f"✅ Лимит установлен!\n"
        f"👤 {person} — {bank}\n"
        f"Было: `{format_number(old_lim)}` грн\n"
        f"Стало: `{format_number(amount)}` грн\n"
        f"🔄 Будет сбрасываться до `{format_number(amount)}` грн каждого 1-го числа",
        parse_mode="Markdown"
    )

async def reset_limits(context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает лимиты 1-го числа каждого месяца"""
    data = load_data()
    limits = load_limits()
    for person in data:
        for bank in data[person]:
            if person in limits and bank in limits[person]:
                data[person][bank]["лимит"] = limits[person][bank]
    save_data(data)
    logging.info("Лимиты сброшены!")

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("set", set_balance_command))
    app.add_handler(CommandHandler("setlimit", set_limit_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Сброс лимитов каждого 1-го числа в 00:01
    app.job_queue.run_monthly(reset_limits, when=time(0, 1), day=1)

    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
