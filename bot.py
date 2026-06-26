import os
import re
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
    "1806fefd802a44a1ad83ebde2b80d8918444678584436536852/"
    "calendar.ics",
)
TZ = ZoneInfo("America/Sao_Paulo")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

NL = chr(10)

AJUDA = (
    "Comandos disponiveis:" + NL +
    "/hoje    - compromissos de hoje" + NL +
    "/amanha  - compromissos de amanha" + NL +
    "/semana  - proximos 7 dias" + NL +
    "/proxima - proxima reuniao do dia" + NL +
    "/livre   - horarios livres hoje"
)

DIAS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


# Calendario
def fetch_calendar():
    r = requests.get(ICAL, timeout=15)
    r.raise_for_status()
    return Calendar.from_ical(r.content)


def extract_teams_link(comp):
    for field in ["LOCATION", "DESCRIPTION"]:
        val = str(comp.get(field, ""))
        match = re.search(r'https://teams\.microsoft\.com/\S+', val)
        if match:
            return match.group(0).rstrip(">")
    return None


def get_events(date_val, cal=None):
    try:
        if cal is None:
            cal = fetch_calendar()
        events = []
        for comp in cal.walk("VEVENT"):
            dt_start = comp["DTSTART"].dt
            d = dt_start.date() if hasattr(dt_start, "date") else dt_start
            if d != date_val:
                continue
            if hasattr(dt_start, "hour"):
                dt_local = dt_start.astimezone(TZ)
                hora = dt_local.strftime("%H:%M")
                dtend_raw = comp.get("DTEND")
                if dtend_raw and hasattr(dtend_raw.dt, "hour"):
                    dt_end = dtend_raw.dt.astimezone(TZ)
                else:
                    dt_end = dt_local + timedelta(hours=1)
            else:
                hora = "Dia todo"
                dt_local = None
                dt_end = None
            titulo = str(comp.get("SUMMARY", "Sem titulo"))
            teams = extract_teams_link(comp)
            events.append((hora, titulo, dt_local, dt_end, teams))
        return sorted(events, key=lambda x: (x[2] is None, x[2] or datetime(1900, 1, 1, tzinfo=TZ)))
    except Exception as e:
        log.error("Erro ao buscar calendario: %s", e)
        return None


def fmt_evento(hora, titulo, teams):
    linha = hora + " - " + titulo
    if teams:
        linha += NL + "   Teams: " + teams
    return linha


def fmt(date_val, label):
    events = get_events(date_val)
    header = "*" + label + " - " + date_val.strftime("%d/%m/%Y") + "*"
    if events is None:
        return header + NL + "Nao consegui acessar o calendario agora."
    if not events:
        return header + NL + "Nenhum compromisso."
    linhas = [header]
    for hora, titulo, _, _, teams in events:
        linhas.append(fmt_evento(hora, titulo, teams))
    return NL.join(linhas)


def fmt_semana(start):
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
            for hora, titulo, _, _, teams in events:
                linhas.append(fmt_evento(hora, titulo, teams))
    if not tem_algum:
        linhas.append("Nenhum compromisso na semana.")
    return NL.join(linhas)


def fmt_proxima():
    now = datetime.now(TZ)
    events = get_events(now.date())
    if events is None:
        return "Nao consegui acessar o calendario agora."
    futuros = [(h, s, dt, dte, teams) for h, s, dt, dte, teams in events if dt and dt > now]
    if not futuros:
        return "Nenhum compromisso restante hoje."
    hora, titulo, dt, _, teams = futuros[0]
    mins = int((dt - now).total_seconds() // 60)
    if mins < 60:
        tempo = "em " + str(mins) + " min"
    else:
        h2 = mins // 60
        m2 = mins % 60
        tempo = "em " + str(h2) + "h" + (str(m2) + "min" if m2 else "")
    linhas = ["*Proxima reuniao*", hora + " - " + titulo + " (" + tempo + ")"]
    if teams:
        linhas.append("Teams: " + teams)
    return NL.join(linhas)


def fmt_livre():
    now = datetime.now(TZ)
    today = now.date()
    events = get_events(today)
    if events is None:
        return "Nao consegui acessar o calendario agora."
    timed = [(dt, dte) for _, _, dt, dte, _ in events if dt is not None]
    inicio = datetime(today.year, today.month, today.day, 8, 0, tzinfo=TZ)
    fim_dia = datetime(today.year, today.month, today.day, 18, 0, tzinfo=TZ)
    cursor = max(inicio, now.replace(minute=0, second=0, microsecond=0))
    livres = []
    for dt_start, dt_end in sorted(timed):
        if dt_start > cursor + timedelta(minutes=15):
            livres.append(cursor.strftime("%H:%M") + " - " + dt_start.strftime("%H:%M"))
        if dt_end and dt_end > cursor:
            cursor = dt_end
    if cursor < fim_dia:
        livres.append(cursor.strftime("%H:%M") + " - 18:00")
    header = "*Horarios livres hoje*"
    if not livres:
        return header + NL + "Agenda cheia hoje."
    return header + NL + NL.join(livres)


def hoje():
    return datetime.now(TZ).date()


# Jobs
async def job_manha(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Bom dia"), parse_mode="Markdown")

async def job_tarde(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Boa tarde"), parse_mode="Markdown")

async def job_noite(ctx):
    await ctx.bot.send_message(CHAT_ID, fmt(hoje(), "Boa noite"), parse_mode="Markdown")

async def job_resumo(ctx):
    amanha = hoje() + timedelta(days=1)
    await ctx.bot.send_message(CHAT_ID, fmt(amanha, "Amanha"), parse_mode="Markdown")

async def job_segunda(ctx):
    if hoje().weekday() == 0:
        await ctx.bot.send_message(CHAT_ID, fmt_semana(hoje()), parse_mode="Markdown")

async def job_lembrete(ctx):
    data = ctx.job.data
    msg = "*Lembrete - em 30 min*" + NL + data["hora"] + " - " + data["titulo"]
    if data["teams"]:
        msg += NL + "Teams: " + data["teams"]
    await ctx.bot.send_message(CHAT_ID, msg, parse_mode="Markdown")

async def job_agendar_lembretes(ctx):
    try:
        cal = fetch_calendar()
        events = get_events(hoje(), cal=cal)
        if not events:
            return
        now = datetime.now(TZ)
        jq = ctx.application.job_queue
        for hora, titulo, dt, _, teams in events:
            if dt is None:
                continue
            lembrete_time = dt - timedelta(minutes=30)
            if lembrete_time <= now:
                continue
            jq.run_once(
                job_lembrete,
                lembrete_time,
                data={"titulo": titulo, "hora": hora, "teams": teams},
            )
            log.info("Lembrete agendado: %s as %s", titulo, lembrete_time.strftime("%H:%M"))
    except Exception as e:
        log.error("Erro ao agendar lembretes: %s", e)


# Handlers
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ola! Sou seu assistente de agenda." + NL + NL + AJUDA)

async def cmd_hoje(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fmt(hoje(), "Hoje"), parse_mode="Markdown")

async def cmd_amanha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fmt(hoje() + timedelta(days=1), "Amanha"), parse_mode="Markdown")

async def cmd_semana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fmt_semana(hoje()), parse_mode="Markdown")

async def cmd_proxima(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fmt_proxima(), parse_mode="Markdown")

async def cmd_livre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fmt_livre(), parse_mode="Markdown")

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.lower()
    if "semana" in t:
        await cmd_semana(update, ctx)
    elif any(w in t for w in ["proxima", "proximo", "agora", "seguinte", "quando"]):
        await cmd_proxima(update, ctx)
    elif any(w in t for w in ["livre", "disponivel", "vago", "espaco", "horario"]):
        await cmd_livre(update, ctx)
    elif any(w in t for w in ["hoje", "agenda", "compromisso", "reuniao"]):
        await cmd_hoje(update, ctx)
    elif any(w in t for w in ["amanha"]):
        await cmd_amanha(update, ctx)
    else:
        await update.message.reply_text("Nao entendi. " + NL + NL + AJUDA)


# Main
def main():
    app = Application.builder().token(TOKEN).build()
    jq  = app.job_queue

    jq.run_daily(job_manha,             dtime(6,  0,  tzinfo=TZ))
    jq.run_daily(job_tarde,             dtime(12, 0,  tzinfo=TZ))
    jq.run_daily(job_noite,             dtime(18, 0,  tzinfo=TZ))
    jq.run_daily(job_resumo,            dtime(21, 30, tzinfo=TZ))
    jq.run_daily(job_segunda,           dtime(7,  0,  tzinfo=TZ))
    jq.run_daily(job_agendar_lembretes, dtime(7,  5,  tzinfo=TZ))

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("hoje",    cmd_hoje))
    app.add_handler(CommandHandler("amanha",  cmd_amanha))
    app.add_handler(CommandHandler("semana",  cmd_semana))
    app.add_handler(CommandHandler("proxima", cmd_proxima))
    app.add_handler(CommandHandler("livre",   cmd_livre))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Bot iniciado.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
