import os
import logging
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)

# Config
TOKEN   = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
ICAL    = os.environ.get(
    "ICAL_URL",
    "https://outlook.office365.com/owa/calendar/"
    "08911477e0364b3ea2cf493cb3f6caae@pontaagro.com/"
    "8de13a300c034847aa3080749d707df613675567947086420949/"
    "calendar.ics",
)
TZ = ZoneInfo("America/Sao_Paulo")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def get_events(date):
    try:
        r = requests.get(ICAL, timeout=15)
        r.raise_for_status()
        cal = Calendar.from_ical(r.content)
        events = []
        for comp in cal.walk("VEVENT"):
            dt = comp["DTSTART"].dt
            d  = dt.date() if hasattr(dt, "date") else dt
            if d != date:
                continue
            hora = dt.astimezone(TZ).strftime("%H:%M") if hasattr(dt, "hour") else "Dia todo"
            titulo = str(comp.get("SUMMARY", "Sem titulo"))
            events.append((hora, titulo))
        return sorted(events)
    except Exception as e:
        log.error("Erro ao buscar calendario: %s", e)
        return None


def fmt(date, titulo):
    events = get_events(date)
    header = f"* {titulo} - {date.strftime('%d/%m/%Y')}*
"
    if events is None:
        return header + "Nao consegui acessar o calendario agora."
    if not events:
        return header + "Nenhum compromisso."
    return header + "
".join(f"{h} - {s}" for h, s in events)


def hoje():
    return datetime.now(TZ).date()


async def job_manha(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Bom dia"), parse_mode="Markdown")

async def job_tarde(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Boa tarde"), parse_mode="Markdown")

async def job_noite(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Boa noite"), parse_mode="Markdown")

async def job_resumo(ctx):
    amanha = hoje() + timedelta(days=1)
    await ctx.bot.send_message(CHAT_ID, fmt(amanha, "Amanha"), parse_mode="Markdown")


async def cmd_start(update, ctx):
    await update.message.reply_text(
        "Ola! Sou seu assistente de agenda.

Comandos:
/hoje
/amanha"
    )

async def cmd_hoje(update, ctx):
    await update.message.reply_text(fmt(hoje(), "Hoje"), parse_mode="Markdown")

async def cmd_amanha(update, ctx):
    amanha = hoje() + timedelta(days=1)
    await update.message.reply_text(fmt(amanha, "Amanha"), parse_mode="Markdown")

async def on_message(update, ctx):
    t = update.message.text.lower()
    if any(w in t for w in ["hoje", "agenda", "compromisso"]):
        await cmd_hoje(update, ctx)
    elif "amanha" in t:
        await cmd_amanha(update, ctx)
    else:
        await update.message.reply_text("Use /hoje ou /amanha.")


def main():
    app = Application.builder().token(TOKEN).build()
    jq  = app.job_queue
    jq.run_daily(job_manha,  dtime(6,  0,  tzinfo=TZ))
    jq.run_daily(job_tarde,  dtime(12, 0,  tzinfo=TZ))
    jq.run_daily(job_noite,  dtime(18, 0,  tzinfo=TZ))
    jq.run_daily(job_resumo, dtime(21, 30, tzinfo=TZ))
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("hoje",   cmd_hoje))
    app.add_handler(CommandHandler("amanha", cmd_amanha))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Bot iniciado.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
