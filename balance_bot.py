import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import json
import os

# Токен бота
TOKEN = "8365170231:AAHM2Z0V0kgR_QDiFqegwb0fC_dSHAd5r2o"

# Файл для хранения балансов
DATA_FILE = "balances.json"

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

def format_number(n):
    return f"{int(n):,}".replace(",", " ")

def get_balance_text(data):
    text = "💰 *Текущие балансы:*\n\n"
    for person, banks in data.items():
        text += f"👤 *{person}:*\n"
        for bank, info in banks.items():
            bal = info["баланс"]
            lim = info["лимит"]
            used_pct = int((bal / lim) * 100)
            bar = "🟢" if used_pct < 70 else "🟡" if used_pct < 90 else "🔴"
            text += f"  {bar} {bank}: `{format_number(bal)}` грн (лимит {format_number(lim)}, {used_pct}%)\n"
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

    # Формат: "+5000 Приват Кристина" или "-5000 Приват Кристина"
    # или "Приват Кристина +5000" или "Приват Кристина -5000"
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

    # Определяем кто person а кто bank
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
        await update.message.reply_text(
            f"❌ У {found_person} нет банка {found_bank}!"
        )
        return

    old_bal = data[found_person][found_bank]["баланс"]
    new_bal = old_bal + amount
    data[found_person][found_bank]["баланс"] = new_bal
    save_data(data)

    lim = data[found_person][found_bank]["лимит"]
    used_pct = int((new_bal / lim) * 100)
    sign = "+" if amount >= 0 else ""
    bar = "🟢" if used_pct < 70 else "🟡" if used_pct < 90 else "🔴"

    await update.message.reply_text(
        f"✅ *Обновлено!*\n"
        f"👤 {found_person} — {found_bank}\n"
        f"Было: `{format_number(old_bal)}` грн\n"
        f"Изменение: `{sign}{format_number(amount)}` грн\n"
        f"Стало: `{format_number(new_bal)}` грн\n"
        f"{bar} Лимит: {format_number(lim)} ({used_pct}% использовано)",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Команды бота:*\n\n"
        "/баланс — показать все балансы\n"
        "/помощь — эта справка\n\n"
        "*Как обновить баланс:*\n"
        "Напишите сумму + банк + имя\n\n"
        "➕ Пополнение:\n"
        "`+5000 Приват Кристина`\n\n"
        "➖ Списание:\n"
        "`-5596 Приват Кристина`\n\n"
        "Или в другом порядке:\n"
        "`Приват Кристина -5596`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить точный баланс: /установить Кристина Приват 75000"""
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "Формат: `/установить Имя Банк Сумма`\n"
            "Пример: `/установить Кристина Приват 75000`",
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

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("баланс", balance_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("помощь", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("установить", set_balance_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
