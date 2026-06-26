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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)


# Calendario
def fetch_calendar():
    r = requests.get(ICAL, timeout=15)
    r.raise_for_status()
    return Calendar.from_ical(r.content)


def get_events(date, cal=None):
    try:
        if cal is None:
            cal = fetch_calendar()
        events = []
        for comp in cal.walk("VEVENT"):
            dt = comp["DTSTART"].dt
            d  = dt.date() if hasattr(dt, "date") else dt
            if d != date:
                continue
            hora = (
                dt.astimezone(TZ).strftime("%H:%M")
                if hasattr(dt, "hour")
                else "Dia todo"
            )
            titulo = str(comp.get("SUMMARY", "Sem titulo"))
            events.append((hora, titulo))
        return sorted(events)
    except Exception as e:
        log.error("Erro ao buscar calendario: %s", e)
        return None


DIAS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


def fmt(date, label):
    events = get_events(date)
    NL = chr(10)
    header = "*" + label + " - " + date.strftime("%d/%m/%Y") + "*"
    if events is None:
        return header + NL + "Nao consegui acessar o calendario agora."
    if not events:
        return header + NL + "Nenhum compromisso."
    linhas = [header]
    for h, s in events:
        linhas.append(h + " - " + s)
    return NL.join(linhas)


def fmt_semana(start):
    NL = chr(10)
    try:
        cal = fetch_calendar()
    except Exception as e:
        log.error("Erro ao buscar calendario: %s", e)
        return "*Semana* - Nao consegui acessar o calendario agora."
    fim = start + timedelta(days=6)
    linhas = ["*Semana - " + start.strftime("%d/%m") + " a " + fim.strftime("%d/%m/%Y") + "*"]
    tem_algum = False
    for i in range(7):
        d = start + timedelta(days=i)
        events = get_events(d, cal=cal)
        dia_label = DIAS_PT[d.weekday()] + " " + d.strftime("%d/%m")
        if events is None:
            linhas.append(NL + "*" + dia_label + "*")
            linhas.append("Erro ao carregar.")
        elif events:
            tem_algum = True
            linhas.append(NL + "*" + dia_label + "*")
            for h, s in events:
                linhas.append(h + " - " + s)
    if not tem_algum:
        linhas.append("Nenhum compromisso na semana.")
    return NL.join(linhas)


def hoje():
    return datetime.now(TZ).date()


# Jobs agendados
async def job_manha(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Bom dia"), parse_mode="Markdown")

async def job_tarde(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Boa tarde"), parse_mode="Markdown")

async def job_noite(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Boa noite"), parse_mode="Markdown")

async def job_resumo(ctx):
    amanha = hoje() + timedelta(days=1)
    await ctx.bot.send_message(CHAT_ID, fmt(amanha, "Amanha"), parse_mode="Markdown")


# Handlers
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ola! Sou seu assistente de agenda."
        " Comandos: /hoje | /amanha | /semana"
    )

async def cmd_hoje(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fmt(hoje(), "Hoje"), parse_mode="Markdown")

async def cmd_amanha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    amanha = hoje() + timedelta(days=1)
    await update.message.reply_text(fmt(amanha, "Amanha"), parse_mode="Markdown")

async def cmd_semana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fmt_semana(hoje()), parse_mode="Markdown")

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.lower()
    if "semana" in t:
        await cmd_semana(update, ctx)
    elif any(w in t for w in ["hoje", "agenda", "compromisso", "reuniao"]):
        await cmd_hoje(update, ctx)
    elif "amanha" in t:
        await cmd_amanha(update, ctx)
    else:
        await update.message.reply_text("Use /hoje, /amanha ou /semana.")


# Main
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
    app.add_handler(CommandHandler("semana", cmd_semana))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Bot iniciado.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
