from aiogram import types
from aiogram.dispatcher import FSMContext
from loader import dp


# Эхо хендлер, куда летят текстовые сообщения без указанного состояния
@dp.message_handler(state=None)
async def bot_echo(message: types.Message):
    await message.answer("Я пока не могу вам ничего ответить на это")


# Эхо хендлер, куда летят ВСЕ сообщения с указанным состоянием
@dp.message_handler(state="*", content_types=types.ContentTypes.ANY)
async def bot_echo_all(message: types.Message, state: FSMContext):
    if message.text:
        state_name = await state.get_state()
        await message.answer(
            "В данный момент я ожидаю от вас другого. Посмотрите в сообщении выше, что именно нужно отправить..."
        )
