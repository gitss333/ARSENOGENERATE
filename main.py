import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from PIL import Image, ImageDraw, ImageFont

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError as e:
    exit(1)


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
FONTS_DIR = "fonts"

AVAILABLE_FONTS = {
    "Roboto": "Roboto-VariableFont_wdth,wght.ttf",
    "Montserrat": "Montserrat-Regular.ttf",
    "Open Sans": "OpenSans-Regular.ttf",
    "Oswald": "Oswald-Regular.ttf",
}


FONT_SIZE = {
    "Малый": 0.05,
    "Средний": 0.1,
    "Большой": 0.15
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class PhotoEditor(StatesGroup):
    waiting_for_image = State()
    waiting_for_font = State()
    waiting_for_font_size = State()
    waiting_for_position = State()

def get_font_path(font_label):
    filename = AVAILABLE_FONTS.get(font_label)
    if not filename:
        return None
    path = os.path.join(FONTS_DIR, filename)
    if os.path.exists(path):
        return path
    return None

def create_main_keyboard():
    kb = [[KeyboardButton(text="Создать фото")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def create_font_keyboard():
    buttons = []
    for label in AVAILABLE_FONTS.keys():
        buttons.append([KeyboardButton(text=label)])
    buttons.append([KeyboardButton(text="Отмена")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def create_font_size_keyboard():
    kb = [
        [KeyboardButton(text="Малый")],
        [KeyboardButton(text="Средний")],
        [KeyboardButton(text="Большой")],
        [KeyboardButton(text="Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def create_position_keyboard():
    kb = [
        [KeyboardButton(text="🔼 Сверху")],
        [KeyboardButton(text="⏹️ По центру")],
        [KeyboardButton(text="🔽 Снизу")],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для создания надписей на фото.\n"
        "Нажми кнопку ниже, чтобы начать.",
        reply_markup=create_main_keyboard()
    )

@dp.message(F.text == "Создать фото")
async def start_process(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(PhotoEditor.waiting_for_image)
    await message.answer(
        "📤 Отправьте мне фотографию для изменения",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(PhotoEditor.waiting_for_image, F.photo)
async def process_image(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    file_id = photo.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    local_path = f"temp_{message.from_user.id}.jpg"
    await bot.download_file(file_path, local_path)
    await state.update_data(image_path=local_path)
    
    await state.set_state(PhotoEditor.waiting_for_font)
    await message.answer(
        "✅ Фото получено!\n"
        "🅰️ Выберите шрифт из списка:",
        reply_markup=create_font_keyboard()
    )

@dp.message(PhotoEditor.waiting_for_font)
async def process_font(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить":
        await state.clear()
        await message.answer("Процесс отменен. Нажмите кнопку ниже для начала рестарта.", reply_markup=create_main_keyboard())
        return
    if message.text not in AVAILABLE_FONTS:
        await message.answer("Пожалуйста, выберите шрифт из предложенных кнопок.")
        return
    
    await state.update_data(font_name=message.text)
    await state.set_state(PhotoEditor.waiting_for_font_size)
    await message.answer(
        "📏 Выберите размер шрифта:",
        reply_markup=create_font_size_keyboard()
    )

@dp.message(PhotoEditor.waiting_for_font_size)
async def process_font_size(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить":
        await state.clear()
        await message.answer("Процесс отменен. /start для перезапуска.", reply_markup=create_main_keyboard())
        return
    if message.text not in FONT_SIZE:
        await message.answer("Пожалуйста, выберите размер из предложенных вариантов.")
        return
    
    await state.update_data(font_size_label=message.text)
    await state.set_state(PhotoEditor.waiting_for_position)
    await message.answer(
        "Где расположим текст?",
        reply_markup=create_position_keyboard()
    )

@dp.message(PhotoEditor.waiting_for_position)
async def process_position(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить":
        await state.clear()
        await message.answer("Процесс отменен. /start для начала заново.", reply_markup=create_main_keyboard())
        return
    
    pos_map = {
        "🔼 Сверху": "top",
        "⏹️ По центру": "center",
        "🔽 Снизу": "bottom"
    }

    if message.text not in pos_map:
        await message.answer("Пожалуйста, выберите позицию из кнопок.")
        return
    
    position = pos_map[message.text]
    await state.update_data(position=position)
    
    await message.answer("⏳ Обрабатываю изображение...")
    await generate_and_send(message, state)
    await state.clear()
    await message.answer("Готово! Хотите создать еще одно? Нажмите кнопку.", reply_markup=create_main_keyboard())

async def generate_and_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    img_path = data['image_path']
    font_label = data['font_name']
    font_size_label = data['font_size_label']
    position = data['position']
    
    text = "АРСЕН"
    
    try:
        img = Image.open(img_path).convert("RGB")
        width, height = img.size
        img_resized = img
        
        draw = ImageDraw.Draw(img_resized)
        
        font_path = get_font_path(font_label)
        if not font_path:
            return
        
        font_size = int(height * FONT_SIZE[font_size_label])
        if font_size < 20: 
            font_size = 20
        font = ImageFont.truetype(font_path, font_size)
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        padding = 20
        
        if position == "top":
            x = (width - text_w) / 2
            y = padding
        elif position == "bottom":
            x = (width - text_w) / 2
            y = height - text_h - padding
        else:
            x = (width - text_w) / 2
            y = (height - text_h) / 2
        
        stroke_width = max(1, int(font_size * 0.03))
        draw.text((x, y), text, font=font, fill="white", stroke_width=stroke_width, stroke_fill="black")
        
        output_path = f"result_{message.from_user.id}.jpg"
        img_resized.save(output_path, quality=95)
        
        photo_file = FSInputFile(output_path)
        await message.answer_photo(
            photo_file, 
        )
        
        os.remove(output_path)
        os.remove(img_path)
        
    except Exception as e:
        logging.error(e)
        await message.answer(f"Произошла ошибка при создании! \n{str(e)}")
        if os.path.exists(img_path):
            os.remove(img_path)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())