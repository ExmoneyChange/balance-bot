import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import json
import os
from datetime import time

# Токен бота
TOKEN = "8365170231:AAHM2Z0V0kgR_QDiFqegwb0fC_dSHAd5r2o"

GROUPS_FILE = "groups.json"

MODE_LIMITS = "limits"
MODE_TURNOVER = "turnover"
MODE_CURRENCY = "currency"

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

def format_usd(n):
    return f"{n:,.2f}".replace(",", " ")

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
                text += f"  {bar} {bank}: `{format_number(bal)}` грн (лимит {format_number(lim)})\n"
            text += "\n"

    elif mode == MODE_TURNOVER:
        text = "💰 *Текущие балансы:*\n\n"
        for name, info in accounts.items():
            bal = info["баланс"]
            turnover = info.get("оборот", 0)
            text += f"  💳 {name}: `{format_number(bal)}` грн (оборот за месяц: {format_number(turnover)} грн)\n"
        text += "\n"

    elif mode == MODE_CURRENCY:
        bal_usd = group.get("balance_usd", 0)
        rate_uah = group.get("rate_uah", 0)
        rate_yuan = group.get("rate_yuan", 0)
        text = (
            f"💵 *Баланс USD:* `{format_usd(bal_usd)}` $\n\n"
            f"📈 Курс грн: `{rate_uah}` грн/$ \n"
            f"📈 Курс юань: `{rate_yuan}` юань/$"
        )

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
    elif mode == MODE_TURNOVER:
        await handle_turnover_mode(update, text, group, accounts, chat_id)
    elif mode == MODE_CURRENCY:
        await handle_currency_mode(update, text, group, chat_id)

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
    lim_line = f"📉 Лимит: `{format_number(old_lim)}` → `{format_number(new_lim)}` грн\n" if amount < 0 else f"📊 Лимит: `{format_number(new_lim)}` грн\n"

    await update.message.reply_text(
        f"✅ *Обновлено!*\n"
        f"👤 {found_person} — {found_bank}\n"
        f"Было: `{format_number(old_bal)}` грн\n"
        f"Изменение: `{sign}{format_number(amount)}` грн\n"
        f"Стало: `{format_number(new_bal)}` грн\n"
        f"{lim_line}"
        f"{bar} Использовано: {used_pct}%",
        parse_mode="Markdown"
    )

async def handle_turnover_mode(update, text, group, accounts, chat_id):
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

async def handle_currency_mode(update, text, group, chat_id):
    # Форматы:
    # +30000 грн  — пополнение гривной (конвертация в USD)
    # -65762 юань — списание юанем (конвертация в USD)
    # +500 usd    — прямое пополнение USD
    # -500 usd    — прямое списание USD

    pattern = r'([+-]?\d+(?:\.\d+)?)\s*(грн|юань|usd|USD|\$)'
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return

    amount_str = match.group(1)
    currency = match.group(2).lower()
    amount = float(amount_str)

    rate_uah = group.get("rate_uah", 0)
    rate_yuan = group.get("rate_yuan", 0)
    old_bal = group.get("balance_usd", 0)

    if currency == "грн":
        if rate_uah == 0:
            await update.message.reply_text("❌ Курс гривны не установлен! Используйте `/setrate 44.45`", parse_mode="Markdown")
            return
        usd_amount = amount / rate_uah
        currency_label = f"{format_number(int(amount))} грн по курсу {rate_uah}"
    elif currency == "юань":
        if rate_yuan == 0:
            await update.message.reply_text("❌ Курс юаня не установлен! Используйте `/setrate yuan 6.63`", parse_mode="Markdown")
            return
        usd_amount = amount / rate_yuan
        currency_label = f"{format_number(int(amount))} юань по курсу {rate_yuan}"
    else:
        usd_amount = amount
        currency_label = f"{format_usd(abs(amount))} USD"

    # Если сумма отрицательная — списание
    if amount < 0:
        usd_amount = -abs(usd_amount)

    new_bal = old_bal + usd_amount
    group["balance_usd"] = new_bal
    save_group(chat_id, group)

    sign = "+" if usd_amount >= 0 else ""
    action = "📥 Пополнение" if usd_amount >= 0 else "📤 Списание"

    await update.message.reply_text(
        f"✅ *Обновлено!*\n"
        f"{action}: {currency_label}\n"
        f"= `{sign}{format_usd(usd_amount)}` $\n\n"
        f"Было: `{format_usd(old_bal)}` $\n"
        f"Стало: `{format_usd(new_bal)}` $",
        parse_mode="Markdown"
    )

async def setrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить курс: /setrate 44.45 или /setrate yuan 6.63"""
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group or group.get("mode") != MODE_CURRENCY:
        await update.message.reply_text("❌ Эта команда только для группы в режиме currency")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Формат:\n`/setrate 44.45` — курс гривны\n`/setrate yuan 6.63` — курс юаня",
            parse_mode="Markdown"
        )
        return

    if args[0].lower() == "yuan":
        rate = float(args[1])
        group["rate_yuan"] = rate
        save_group(chat_id, group)
        await update.message.reply_text(f"✅ Курс юаня установлен: `{rate}` юань/$", parse_mode="Markdown")
    else:
        rate = float(args[0])
        group["rate_uah"] = rate
        save_group(chat_id, group)
        await update.message.reply_text(f"✅ Курс гривны установлен: `{rate}` грн/$", parse_mode="Markdown")

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or args[0] not in ["limits", "turnover", "currency"]:
        await update.message.reply_text(
            "Выберите режим группы:\n\n"
            "/setup limits — балансы с лимитами\n"
            "/setup turnover — балансы с оборотом\n"
            "/setup currency — баланс в USD с конвертацией",
            parse_mode="Markdown"
        )
        return

    chat_id = update.effective_chat.id
    mode = args[0]
    group = get_group(chat_id) or {}
    group["mode"] = mode
    if mode == MODE_CURRENCY:
        group.setdefault("balance_usd", 0)
        group.setdefault("rate_uah", 0)
        group.setdefault("rate_yuan", 0)
    else:
        group.setdefault("accounts", {})
    save_group(chat_id, group)

    modes = {"limits": "лимиты", "turnover": "оборот", "currency": "USD конвертация"}
    hints = {
        "limits": "`/addperson Имя`\nЗатем: `/addbank Имя Банк Лимит`",
        "turnover": "`/addaccount МТ 66740`",
        "currency": "`/setrate 44.45` — курс гривны\n`/setrate yuan 6.63` — курс юаня"
    }

    await update.message.reply_text(
        f"✅ Режим установлен: *{modes[mode]}*\n\n{hints[mode]}",
        parse_mode="Markdown"
    )

async def addperson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        return
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Формат: `/addbank Имя Банк Лимит`", parse_mode="Markdown")
        return
    person, bank, limit_str = args[0], args[1], args[2]
    limit = int(limit_str)
    if person not in group["accounts"]:
        await update.message.reply_text(f"❌ Сначала: `/addperson {person}`", parse_mode="Markdown")
        return
    group["accounts"][person][bank] = {"баланс": 0, "лимит": limit, "лимит_макс": limit}
    save_group(chat_id, group)
    await update.message.reply_text(f"✅ Банк *{bank}* для *{person}*\nЛимит: `{format_number(limit)}` грн", parse_mode="Markdown")

async def addaccount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        return
    args = context.args
    if len(args) not in [1, 2]:
        await update.message.reply_text("Формат: `/addaccount Название Баланс`", parse_mode="Markdown")
        return
    name = args[0]
    balance = int(args[1]) if len(args) == 2 else 0
    group["accounts"][name] = {"баланс": balance, "оборот": 0}
    save_group(chat_id, group)
    await update.message.reply_text(f"✅ Счёт *{name}*\nБаланс: `{format_number(balance)}` грн", parse_mode="Markdown")

async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group = get_group(chat_id)
    if not group:
        return
    args = context.args
    mode = group.get("mode", MODE_LIMITS)

    if mode == MODE_CURRENCY:
        if len(args) != 1:
            await update.message.reply_text("Формат: `/set 20000`", parse_mode="Markdown")
            return
        old = group.get("balance_usd", 0)
        group["balance_usd"] = float(args[0])
        save_group(chat_id, group)
        await update.message.reply_text(f"✅ Баланс USD\nБыло: `{format_usd(old)}` $ → Стало: `{format_usd(float(args[0]))}` $", parse_mode="Markdown")
    elif mode == MODE_LIMITS:
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
        await update.message.reply_text(f"✅ {person} — {bank}\n`{format_number(old)}` → `{format_number(int(amount_str))}` грн", parse_mode="Markdown")
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
        await update.message.reply_text(f"✅ {name}\n`{format_number(old)}` → `{format_number(int(amount_str))}` грн", parse_mode="Markdown")

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"✅ Лимит {person} — {bank}\n`{format_number(old_lim)}` → `{format_number(amount)}` грн\n🔄 Сброс 1-го числа",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Команды бота:*\n\n"
        "*Настройка:*\n"
        "/setup limits — режим с лимитами\n"
        "/setup turnover — режим с оборотом\n"
        "/setup currency — режим USD\n"
        "/addperson Имя\n"
        "/addbank Имя Банк Лимит\n"
        "/addaccount Название Баланс\n\n"
        "*Управление:*\n"
        "/balance — балансы\n"
        "/set — установить баланс\n"
        "/setlimit Имя Банк Сумма\n"
        "/setrate 44.45 — курс гривны\n"
        "/setrate yuan 6.63 — курс юаня\n\n"
        "*Сообщения:*\n"
        "`-5596 Приват Кристина`\n"
        "`МТ +23500`\n"
        "`+30000 грн` / `-65762 юань` / `+500 usd`\n\n"
        "🔄 Сброс 1-го числа каждого месяца"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def reset_monthly(context: ContextTypes.DEFAULT_TYPE):
    groups = load_groups()
    for chat_id, group in groups.items():
        mode = group.get("mode", MODE_LIMITS)
        if mode == MODE_LIMITS:
            for person in group.get("accounts", {}):
                for bank in group["accounts"][person]:
                    max_lim = group["accounts"][person][bank].get("лимит_макс", group["accounts"][person][bank]["лимит"])
                    group["accounts"][person][bank]["лимит"] = max_lim
        elif mode == MODE_TURNOVER:
            for name in group.get("accounts", {}):
                group["accounts"][name]["оборот"] = 0
        groups[chat_id] = group
    save_groups(groups)
    logging.info("Сброс выполнен!")

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
    app.add_handler(CommandHandler("setrate", setrate_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_monthly(reset_monthly, when=time(0, 1), day=1)

    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
