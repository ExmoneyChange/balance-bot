import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import json
import os
from datetime import time

# Токен бота
TOKEN = "8365170231:AAHM2Z0V0kgR_QDiFqegwb0fC_dSHAd5r2o"

# Файлы данных
GROUPS_FILE = "groups.json"

# Режимы групп
MODE_LIMITS = "limits"    # Группа 1: балансы + лимиты
MODE_TURNOVER = "turnover"  # Группа 2: балансы + оборот

def load_groups():
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_groups(groups):
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)

def get_group(chat_id):
    groups = load_groups()
    return groups.get(str(chat_id))

def save_group(chat_id, data):
    groups = load_groups()
    groups[str(chat_id)] = data
    save_groups(groups)

def format_number(n):
    return f"{int(n):,}".replace(",", " ")

def get_balance_text(group):
    mode = group.get("mode", MODE_LIMITS)
    accounts = group.get("accounts", {})
    
    if mode == MODE_LIMITS:
        text = "💰 *Текущие балансы:*\n\n"
        for person, banks in accounts.items():
            text += f"👤 *{person}:*\n"
            for bank, info in banks.items():
                bal = info["баланс"]
                lim = info["лимит"]
                default_lim = info.get("лимит_макс", lim)
                used_pct = int(((default_lim - lim) / default_lim) * 100) if default_lim > 0 else 0
                bar = "🟢" if used_pct < 70 else "🟡" if used_pct < 90 else "🔴"
                text += f"  {bar} {bank}: `{format_number(bal)}` грн (лимит остаток {format_number(lim)}, {used_pct}%)\n"
            text += "\n"
    else:  # MODE_TURNOVER
        text = "💰 *Текущие балансы:*\n\n"
        for name, info in accounts.items():
            bal = info["баланс"]
            turnover = info.get("оборот", 0)
            text += f"  💳 {name}: `{format_number(bal)}` грн (оборот за месяц: {format_number(turnover)} грн)\n"
        text += "\n"
    
    return text

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        await update.message.reply_text("❌ Группа не настроена. Используйте /setup")
        return
    text = get_balance_text(group)
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        return

    text = update.message.text.strip()
    mode = group.get("mode", MODE_LIMITS)
    accounts = group.get("accounts", {})

    if mode == MODE_LIMITS:
        await handle_limits_mode(update, text, group, accounts, chat_id)
    else:
        await handle_turnover_mode(update, text, group, accounts, chat_id)

async def handle_limits_mode(update, text, group, accounts, chat_id):
    pattern = r'([+-]?\d+)\s+([\wа-яёА-ЯЁ]+)\s+([\wа-яёА-ЯЁ]+)|' \
              r'([\wа-яёА-ЯЁ]+)\s+([\wа-яёА-ЯЁ]+)\s+([+-]?\d+)'
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return

    if match.group(1):
        amount_str, word1, word2 = match.group(1), match.group(2), match.group(3)
    else:
        word1, word2, amount_str = match.group(4), match.group(5), match.group(6)

    amount = int(amount_str)

    persons = list(accounts.keys())
    banks_all = list(set(b for p in persons for b in accounts[p].keys()))

    found_person = found_bank = None
    for w in [word1, word2]:
        for person in persons:
            if person.lower() == w.lower():
                found_person = person
        for bank in banks_all:
            if bank.lower() == w.lower():
                found_bank = bank

    if not found_person or not found_bank:
        return
    if found_bank not in accounts.get(found_person, {}):
        await update.message.reply_text(f"❌ У {found_person} нет банка {found_bank}!")
        return

    info = accounts[found_person][found_bank]
    old_bal = info["баланс"]
    old_lim = info["лимит"]
    new_bal = old_bal + amount
    new_lim = max(0, old_lim + amount) if amount < 0 else old_lim

    accounts[found_person][found_bank]["баланс"] = new_bal
    accounts[found_person][found_bank]["лимит"] = new_lim
    group["accounts"] = accounts
    save_group(chat_id, group)

    default_lim = info.get("лимит_макс", old_lim)
    used_pct = int(((default_lim - new_lim) / default_lim) * 100) if default_lim > 0 else 0
    sign = "+" if amount >= 0 else ""
    bar = "🟢" if used_pct < 70 else "🟡" if used_pct < 90 else "🔴"
    lim_line = f"📉 Лимит: `{format_number(old_lim)}` → `{format_number(new_lim)}` грн\n" if amount < 0 else f"📊 Лимит остаток: `{format_number(new_lim)}` грн\n"

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

async def handle_turnover_mode(update, text, group, accounts, chat_id):
    # Формат: "МТ +23500" или "МТ -11250" или "+23500 МТ"
    pattern = r'([\wа-яёА-ЯЁ]+)\s+([+-]?\d+)|([+-]?\d+)\s+([\wа-яёА-ЯЁ]+)'
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return

    if match.group(1):
        name, amount_str = match.group(1), match.group(2)
    else:
        amount_str, name = match.group(3), match.group(4)

    amount = int(amount_str)

    found_name = None
    for acc_name in accounts.keys():
        if acc_name.lower() == name.lower():
            found_name = acc_name
            break

    if not found_name:
        return

    old_bal = accounts[found_name]["баланс"]
    old_turnover = accounts[found_name].get("оборот", 0)
    new_bal = old_bal + amount
    new_turnover = old_turnover + amount if amount > 0 else old_turnover

    accounts[found_name]["баланс"] = new_bal
    accounts[found_name]["оборот"] = new_turnover
    group["accounts"] = accounts
    save_group(chat_id, group)

    sign = "+" if amount >= 0 else ""
    turnover_line = f"📈 Оборот за месяц: `{format_number(new_turnover)}` грн\n" if amount > 0 else ""

    await update.message.reply_text(
        f"✅ *Обновлено!*\n"
        f"💳 {found_name}\n"
        f"Было: `{format_number(old_bal)}` грн\n"
        f"Изменение: `{sign}{format_number(amount)}` грн\n"
        f"Стало: `{format_number(new_bal)}` грн\n"
        f"{turnover_line}",
        parse_mode="Markdown"
    )

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройка группы. /setup limits или /setup turnover"""
    args = context.args
    if not args or args[0] not in ["limits", "turnover"]:
        await update.message.reply_text(
            "Выберите режим группы:\n\n"
            "/setup limits — балансы с лимитами\n"
            "/setup turnover — балансы с оборотом",
            parse_mode="Markdown"
        )
        return

    chat_id = update.effective_chat.id
    mode = args[0]
    group = get_group(chat_id) or {"mode": mode, "accounts": {}}
    group["mode"] = mode
    save_group(chat_id, group)

    await update.message.reply_text(
        f"✅ Режим установлен: *{'лимиты' if mode == 'limits' else 'оборот'}*\n\n"
        f"Теперь добавьте участников:\n"
        + ("`/addperson Имя`\nЗатем: `/addbank Имя Банк Лимит`" if mode == "limits" else "`/addaccount МТ 66740`"),
        parse_mode="Markdown"
    )

async def addperson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить участника: /addperson Кристина"""
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        await update.message.reply_text("❌ Сначала настройте группу: /setup limits")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Формат: `/addperson Имя`", parse_mode="Markdown")
        return

    person = args[0]
    if person not in group["accounts"]:
        group["accounts"][person] = {}
        save_group(chat_id, group)
        await update.message.reply_text(f"✅ Добавлен участник: *{person}*\nТеперь: `/addbank {person} Банк Лимит`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Участник {person} уже есть!")

async def addbank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить банк: /addbank Кристина Приват 350000"""
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        await update.message.reply_text("❌ Сначала настройте группу: /setup limits")
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Формат: `/addbank Имя Банк Лимит`\nПример: `/addbank Кристина Приват 350000`", parse_mode="Markdown")
        return

    person, bank, limit_str = args[0], args[1], args[2]
    limit = int(limit_str)

    if person not in group["accounts"]:
        await update.message.reply_text(f"❌ Сначала добавьте участника: `/addperson {person}`", parse_mode="Markdown")
        return

    group["accounts"][person][bank] = {"баланс": 0, "лимит": limit, "лимит_макс": limit}
    save_group(chat_id, group)
    await update.message.reply_text(f"✅ Добавлен банк *{bank}* для *{person}*\nЛимит: `{format_number(limit)}` грн", parse_mode="Markdown")

async def addaccount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить счёт для режима оборота: /addaccount МТ 66740"""
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        await update.message.reply_text("❌ Сначала настройте группу: /setup turnover")
        return

    args = context.args
    if len(args) not in [1, 2]:
        await update.message.reply_text("Формат: `/addaccount Название Баланс`\nПример: `/addaccount МТ 66740`", parse_mode="Markdown")
        return

    name = args[0]
    balance = int(args[1]) if len(args) == 2 else 0
    group["accounts"][name] = {"баланс": balance, "оборот": 0}
    save_group(chat_id, group)
    await update.message.reply_text(f"✅ Добавлен счёт *{name}*\nБаланс: `{format_number(balance)}` грн", parse_mode="Markdown")

async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить баланс"""
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        return

    args = context.args
    mode = group.get("mode", MODE_LIMITS)

    if mode == MODE_LIMITS:
        if len(args) != 3:
            await update.message.reply_text("Формат: `/set Имя Банк Сумма`", parse_mode="Markdown")
            return
        person, bank, amount_str = args[0], args[1], args[2]
        if person not in group["accounts"] or bank not in group["accounts"][person]:
            await update.message.reply_text("❌ Не найдено!")
            return
        old = group["accounts"][person][bank]["баланс"]
        group["accounts"][person][bank]["баланс"] = int(amount_str)
        save_group(chat_id, group)
        await update.message.reply_text(f"✅ Баланс {person} — {bank}\nБыло: `{format_number(old)}` → Стало: `{format_number(int(amount_str))}` грн", parse_mode="Markdown")
    else:
        if len(args) != 2:
            await update.message.reply_text("Формат: `/set Название Сумма`", parse_mode="Markdown")
            return
        name, amount_str = args[0], args[1]
        if name not in group["accounts"]:
            await update.message.reply_text("❌ Не найдено!")
            return
        old = group["accounts"][name]["баланс"]
        group["accounts"][name]["баланс"] = int(amount_str)
        save_group(chat_id, group)
        await update.message.reply_text(f"✅ Баланс {name}\nБыло: `{format_number(old)}` → Стало: `{format_number(int(amount_str))}` грн", parse_mode="Markdown")

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить лимит: /setlimit Кристина Приват 400000"""
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Формат: `/setlimit Имя Банк Сумма`", parse_mode="Markdown")
        return

    person, bank, amount_str = args[0], args[1], args[2]
    amount = int(amount_str)

    if person not in group["accounts"] or bank not in group["accounts"][person]:
        await update.message.reply_text("❌ Не найдено!")
        return

    old_lim = group["accounts"][person][bank]["лимит"]
    group["accounts"][person][bank]["лимит"] = amount
    group["accounts"][person][bank]["лимит_макс"] = amount
    save_group(chat_id, group)

    await update.message.reply_text(
        f"✅ Лимит установлен!\n"
        f"👤 {person} — {bank}\n"
        f"Было: `{format_number(old_lim)}` → Стало: `{format_number(amount)}` грн\n"
        f"🔄 Сброс 1-го числа каждого месяца",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Команды бота:*\n\n"
        "*Настройка группы:*\n"
        "/setup limits — режим с лимитами\n"
        "/setup turnover — режим с оборотом\n"
        "/addperson Имя — добавить участника\n"
        "/addbank Имя Банк Лимит — добавить банк\n"
        "/addaccount Название Баланс — добавить счёт\n\n"
        "*Управление:*\n"
        "/balance — показать балансы\n"
        "/set — установить баланс\n"
        "/setlimit Имя Банк Сумма — изменить лимит\n"
        "/help — эта справка\n\n"
        "*Обновление баланса:*\n"
        "`-5596 Приват Кристина` — списание\n"
        "`+5000 Приват Кристина` — пополнение\n"
        "`МТ +23500` — для режима оборота\n\n"
        "🔄 Лимиты/обороты сбрасываются 1-го числа"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def reset_monthly(context: ContextTypes.DEFAULT_TYPE):
    """Сброс лимитов и оборотов 1-го числа"""
    groups = load_groups()
    for chat_id, group in groups.items():
        mode = group.get("mode", MODE_LIMITS)
        accounts = group.get("accounts", {})
        if mode == MODE_LIMITS:
            for person in accounts:
                for bank in accounts[person]:
                    max_lim = accounts[person][bank].get("лимит_макс", accounts[person][bank]["лимит"])
                    accounts[person][bank]["лимит"] = max_lim
        else:
            for name in accounts:
                accounts[name]["оборот"] = 0
        group["accounts"] = accounts
        groups[chat_id] = group
    save_groups(groups)
    logging.info("Лимиты и обороты сброшены!")

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CommandHandler("addperson", addperson_command))
    app.add_handler(CommandHandler("addbank", addbank_command))
    app.add_handler(CommandHandler("addaccount", addaccount_command))
    app.add_handler(CommandHandler("set", set_balance_command))
    app.add_handler(CommandHandler("setlimit", set_limit_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_monthly(reset_monthly, when=time(0, 1), day=1)

    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
