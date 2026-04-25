"""
FormFlow — бэкенд сервер + статика
Запуск: uvicorn main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import uuid
import random
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import os

app = FastAPI(title="FormFlow API", version="1.0.0")

# CORS — разрешаем запросы с любого источника (для разработки)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Шаблоны (папка templates с index.html)
templates = Jinja2Templates(directory="templates")

# Хранилище задач в памяти (для Railway — подойдёт, но при рестарте теряется)
tasks: dict = {}

# ── Модели запросов ──
class TaskCreate(BaseModel):
    url: str
    platform: str            # "yandex" | "google"
    count: int
    profile: str             # "students" | "adults" | "mixed"
    answers: Optional[dict] = {}

class TaskStatus(BaseModel):
    task_id: str
    status: str
    done: int
    total: int
    percent: int
    started_at: Optional[str]
    finished_at: Optional[str]
    error: Optional[str]

# ── Главная страница ──
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ── API ──
@app.post("/api/task", response_model=TaskStatus)
async def create_task(body: TaskCreate):
    if not body.url.startswith("http"):
        raise HTTPException(400, "Некорректная ссылка")
    if body.count < 1 or body.count > 500:
        raise HTTPException(400, "Количество от 1 до 500")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "done": 0,
        "total": body.count,
        "percent": 0,
        "url": body.url,
        "platform": body.platform,
        "profile": body.profile,
        "answers": body.answers,
        "started_at": None,
        "finished_at": None,
        "error": None,
    }
    asyncio.create_task(run_task(task_id))
    return tasks[task_id]

@app.get("/api/task/{task_id}", response_model=TaskStatus)
def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Задача не найдена")
    return tasks[task_id]

@app.delete("/api/task/{task_id}")
def cancel_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Задача не найдена")
    tasks[task_id]["status"] = "cancelled"
    return {"message": "Отменено"}

# ── Фоновая задача с Playwright ──
async def run_task(task_id: str):
    task = tasks[task_id]
    task["status"] = "running"
    task["started_at"] = datetime.utcnow().isoformat()

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            for i in range(task["total"]):
                if task["status"] == "cancelled":
                    break

                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )
                context = await browser.new_context(
                    viewport={"width": random.randint(1280, 1920), "height": random.randint(700, 1080)},
                    locale="ru-RU",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                try:
                    if task["platform"] == "yandex":
                        await fill_yandex(page, task["url"], task["answers"], task["profile"])
                    else:
                        await fill_google(page, task["url"], task["answers"], task["profile"])
                    task["done"] += 1
                    task["percent"] = round(task["done"] / task["total"] * 100)
                except Exception as e:
                    print(f"[{task_id}] Ошибка в прохождении {i+1}: {e}")
                finally:
                    await context.close()
                    await browser.close()

                if i < task["total"] - 1:
                    await asyncio.sleep(random.uniform(5, 12))

        task["status"] = "done"
    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
    finally:
        task["finished_at"] = datetime.utcnow().isoformat()

# ── Функции заполнения (оставлены без изменений, но для краткости сокращены) ──
OPEN_ANSWERS = ["Всё устраивает", "Хороший сервис", "Пользуюсь давно", "Интересный продукт", "Удобно"]
PROFILE_BIAS = {
    "students": {"scale_min": 0.5, "scale_max": 0.9},
    "adults":   {"scale_min": 0.4, "scale_max": 0.8},
    "mixed":    {"scale_min": 0.3, "scale_max": 1.0},
}

async def human_delay(min_s=0.5, max_s=2.0):
    await asyncio.sleep(random.uniform(min_s, max_s))

async def fill_yandex(page, url, answers, profile):
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await human_delay(1.5, 3.0)
    bias = PROFILE_BIAS.get(profile, PROFILE_BIAS["mixed"])
    # ... (оставляем ваш код, он рабочий)
    # Вставьте сюда полный код fill_yandex из вашего main.py
    # Для краткости в ответе я не копирую, вы вставите свой
    
    # Радиокнопки
    blocks = await page.query_selector_all(".form-question")
    for block in blocks:
        q_el = await block.query_selector(".form-question__title")
        q_text = (await q_el.inner_text()).lower() if q_el else ""

        chosen = None
        for keyword, options in answers.items():
            if keyword.lower() in q_text:
                chosen = random.choice(options)
                break

        radios = await block.query_selector_all(".radio-button__radio")
        if radios:
            if chosen:
                for r in radios:
                    lbl = await r.query_selector(".radio-button__text")
                    txt = (await lbl.inner_text()) if lbl else ""
                    if chosen.lower() in txt.lower():
                        await r.click(); break
                else:
                    await random.choice(radios).click()
            else:
                await random.choice(radios).click()
            await human_delay(0.4, 1.2)

    # Шкалы
    scales = await page.query_selector_all(".scale-control__button")
    if scales:
        idx_min = int(len(scales) * bias["scale_min"])
        idx_max = int(len(scales) * bias["scale_max"])
        await random.choice(scales[idx_min:idx_max+1]).click()
        await human_delay(0.3, 0.8)

    # Чекбоксы
    checkboxes = await page.query_selector_all(".checkbox__box")
    if checkboxes:
        n = min(random.randint(1, 3), len(checkboxes))
        for cb in random.sample(checkboxes, n):
            await cb.click()
            await human_delay(0.2, 0.6)

    # Текстовые поля
    inputs = await page.query_selector_all("textarea, input[type='text']")
    for inp in inputs:
        if await inp.is_visible():
            text = random.choice(OPEN_ANSWERS)
            await inp.click()
            for ch in text:
                await inp.type(ch, delay=random.randint(40, 110))
            await human_delay(0.5, 1.5)

    # Отправка
    submit = await page.query_selector(
        "button[type='submit'], .form-submit__button, button:has-text('Отправить')"
    )
    if submit:
        await human_delay(1.0, 2.5)
        await submit.click()
        await page.wait_for_load_state("networkidle", timeout=15000)


# ── Заполнение Google Forms ──
async def fill_google(page, url, answers, profile):
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await human_delay(2.0, 4.0)
    # ... (ваш код fill_google)
    
    bias = PROFILE_BIAS.get(profile, PROFILE_BIAS["mixed"])

    # Радиокнопки (один вариант)
    radio_groups = await page.query_selector_all('[role="radiogroup"]')
    for group in radio_groups:
        # Пробуем найти нужный ответ
        q_el = await group.query_selector('[role="heading"]')
        q_text = (await q_el.inner_text()).lower() if q_el else ""

        chosen = None
        for keyword, options in answers.items():
            if keyword.lower() in q_text:
                chosen = random.choice(options)
                break

        radios = await group.query_selector_all('[role="radio"]')
        if radios:
            if chosen:
                for r in radios:
                    lbl = await r.get_attribute("data-value") or ""
                    if chosen.lower() in lbl.lower():
                        await r.click(); break
                else:
                    await random.choice(radios).click()
            else:
                await random.choice(radios).click()
            await human_delay(0.4, 1.0)

    # Чекбоксы
    checkbox_groups = await page.query_selector_all('[role="group"]')
    for group in checkbox_groups:
        boxes = await group.query_selector_all('[role="checkbox"]')
        if boxes:
            n = min(random.randint(1, 2), len(boxes))
            for cb in random.sample(boxes, n):
                await cb.click()
                await human_delay(0.2, 0.5)

    # Шкалы (linear scale)
    scale_groups = await page.query_selector_all('[role="radiogroup"]')
    for group in scale_groups:
        options = await group.query_selector_all('[role="radio"]')
        if len(options) >= 5:
            idx_min = int(len(options) * bias["scale_min"])
            idx_max = int(len(options) * bias["scale_max"])
            await random.choice(options[idx_min:idx_max+1]).click()
            await human_delay(0.3, 0.8)

    # Текстовые поля
    text_areas = await page.query_selector_all('textarea, input[type="text"]')
    for inp in text_areas:
        if await inp.is_visible():
            text = random.choice(OPEN_ANSWERS)
            await inp.click()
            for ch in text:
                await inp.type(ch, delay=random.randint(40, 110))
            await human_delay(0.5, 1.5)

    # Кнопка «Отправить»
    submit = await page.query_selector(
        '[role="button"]:has-text("Отправить"), '
        '[role="button"]:has-text("Submit"), '
        'div[jsname="M2UYVd"]'
    )
    if submit:
        await human_delay(1.0, 2.5)
        await submit.click()
        await page.wait_for_load_state("networkidle", timeout=15000)
