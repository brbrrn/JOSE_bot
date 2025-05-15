import os
import re
import io
from telebot import TeleBot, types
from telebot.types import ReplyKeyboardRemove, BotCommand
from opensubtitlescom import OpenSubtitles
from langs import LANGS, MESSAGES

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = TeleBot('Token')

subtitles = OpenSubtitles("SUBstitute v1.0", "Key")
subtitles.login('log', 'pass')

user_locale = {}     # chat.id -> 'ru' / 'en' / 'it'
user_language = {}   # chat.id -> subtitle language (en, ru, etc.)
query_cache = {}     # (query, season, episode, lang) -> subtitle

#commands
bot.set_my_commands([
    BotCommand("start", "Start the bot"),
])

#languages
def get_locale(chat_id):
    return user_locale.get(chat_id, 'en')

def send_main_menu(message):
    lang = get_locale(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton(MESSAGES['search_button'][lang]),
        types.KeyboardButton(MESSAGES['choose_lang_button'][lang]),
    )
    bot.send_message(message.chat.id, MESSAGES['menu_prompt'][lang], reply_markup=markup)

# ====== Старт ======
@bot.message_handler(commands=['start', 'hello'])
def start_handler(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for code, label in LANGS.items():
        markup.add(types.KeyboardButton(label))
    bot.send_message(message.chat.id, MESSAGES['choose_menu_lang']['en'], reply_markup=markup)
    bot.register_next_step_handler(message, save_interface_language)

def save_interface_language(message):
    selected = message.text
    for code, label in LANGS.items():
        if selected == label:
            user_locale[message.chat.id] = code
            bot.send_message(message.chat.id, MESSAGES['lang_saved'][code], reply_markup=ReplyKeyboardRemove())
            send_main_menu(message)
            return
    bot.send_message(message.chat.id, "Please select a valid language.")
    start_handler(message)

@bot.message_handler(func=lambda msg: any(x in msg.text for x in ["Язык", "Language", "Lingua", "Langue", "Sprache", "Idioma"]))
def change_language(message):
    start_handler(message)

# ====== Поиск ======
@bot.message_handler(func=lambda msg: msg.text in (
    MESSAGES['search_button']['en'], MESSAGES['search_button']['ru'], MESSAGES['search_button']['it'], MESSAGES['search_button']['fr'], MESSAGES['search_button']['de'], MESSAGES['search_button']['es'],
))
def start_search(message):
    lang = get_locale(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    langs = ["en", "ru", "fr", "es", "de", "it"]
    buttons = [types.KeyboardButton(lang.upper()) for lang in langs]
    markup.add(*buttons)
    bot.send_message(message.chat.id, MESSAGES['choose_sub_lang'][lang], reply_markup=markup)
    bot.register_next_step_handler(message, choose_language)

def choose_language(message):
    lang = message.text.strip().lower()
    if lang not in ["en", "ru", "fr", "es", "de", "it"]:
        bot.send_message(message.chat.id, "Invalid language. Please choose again.")
        return start_search(message)
    user_language[message.chat.id] = lang
    user_locale.setdefault(message.chat.id, 'en')  # fallback if unset
    bot.send_message(
        message.chat.id,
        MESSAGES['enter_show'][get_locale(message.chat.id)].format(lang.upper()),
        reply_markup=ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(message, fetch_search)

def fetch_search(message):
    chat_id = message.chat.id
    lang = user_language.get(chat_id, "en")
    locale = get_locale(chat_id)
    text = message.text.strip()

    match = re.search(r'(.*?)[\s\-]*(S(\d{2})E(\d{2}))', text, re.IGNORECASE)
    if match:
        show_name = match.group(1).strip()
        season = int(match.group(3))
        episode = int(match.group(4))
    else:
        show_name = text
        season = None
        episode = None

    cache_key = (show_name.lower(), season, episode, lang)
    if cache_key in query_cache:
            subtitle = query_cache[cache_key]
    else:
        try:
            response = subtitles.search(
                query=show_name,
                season_number=season,
                episode_number=episode,
                languages=lang)
            if not response.data:
                bot.send_message(chat_id, MESSAGES['not_found'][locale].format(show_name))
                return send_main_menu(message)
            subtitle = response.data[0]
            query_cache[cache_key] = subtitle
        except Exception as e:
            bot.send_message(chat_id, f"{MESSAGES['error'][locale]}: {e}")
            return send_main_menu(message)

    subtitle_url = subtitle.url
    files = getattr(subtitle, 'files', [])
    file_id = files[0].get('file_id') if files else None

    if file_id:
        try:
            file_bytes = subtitles.download(file_id)
            file_stream = io.BytesIO(file_bytes)
            file_name = f"{show_name}_S{season:02d}E{episode:02d}.srt" if season and episode else f"{show_name}.srt"
            file_stream.name = file_name
            bot.send_document(chat_id, file_stream)
            return send_main_menu(message)
        except Exception as e:
            bot.send_message(chat_id, f"{MESSAGES['download_failed'][locale]}: {e}")
    bot.send_message(chat_id, f"*{MESSAGES['found'][locale]}*\n[Download Link]({subtitle_url})", parse_mode='Markdown')
    send_main_menu(message)

# ====== Запуск ======
bot.infinity_polling()
