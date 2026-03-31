"""Text helpers shared across services."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Iterable, List

from langchain_text_splitters import RecursiveCharacterTextSplitter

MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def split_documents(documents, chunk_size=500, chunk_overlap=100):
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_documents(documents)


def docs_to_fulltext(documents: Iterable) -> str:
    return clean_text("\n\n".join(d.page_content for d in documents))


def duration_question(question: str) -> bool:
    q = question.lower()
    keywords = ["how many months", "duration", "how long", "total time", "last", "internship lasted"]
    return any(k in q for k in keywords)


def parse_date_from_text(text: str):
    text = text.lower()
    pattern = (
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"(\d{1,2})(?:,)?\s+(20\d{2})"
    )
    matches = re.findall(pattern, text)

    dates: List[datetime] = []
    for month_name, day, year in matches:
        try:
            dt = datetime(int(year), MONTH_MAP[month_name], int(day))
            dates.append(dt)
        except Exception:
            continue
    return dates


def compute_duration(start: datetime, end: datetime):
    if end < start:
        start, end = end, start

    days = (end - start).days
    weeks = round(days / 7, 1)

    from dateutil.relativedelta import relativedelta

    rd = relativedelta(end, start)
    months = rd.years * 12 + rd.months

    return {"months": months, "weeks": weeks, "days": days}


def enrich_answer_if_duration(question: str, context: str, base_answer: str) -> str:
    if not duration_question(question):
        return base_answer

    dates = parse_date_from_text(context)
    if len(dates) >= 2:
        start_date = dates[0]
        end_date = dates[1]
        dur = compute_duration(start_date, end_date)
        return (
            f"The internship lasted {dur['months']} months (~{dur['weeks']} weeks, {dur['days']} days) "
            f"({start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')})."
        )
    return base_answer


def is_address_question(question: str) -> bool:
    q = question.lower()
    return ("address" in q) or ("located" in q) or ("location" in q)


def is_email_question(question: str) -> bool:
    q = question.lower()
    return ("email" in q) or ("mail id" in q) or ("gmail" in q)


def is_phone_question(question: str) -> bool:
    q = question.lower()
    return ("phone" in q) or ("mobile" in q) or ("contact" in q)


def extract_email(text: str):
    match = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return match[0] if match else None


def extract_phone(text: str):
    match = re.findall(r"(?:\+?\d{1,3}[-\s]?)?\b\d{10}\b", text)
    return match[0] if match else None


def extract_address_like_chunk(text: str):
    t = clean_text(text)
    low = t.lower()

    markers = [
        "address:",
        "registered office",
        "corporate office",
        "head office",
        "office address",
    ]

    for marker in markers:
        idx = low.find(marker)
        if idx != -1:
            start = max(0, idx - 50)
            end = min(len(t), idx + 400)
            return t[start:end].strip()

    pin_match = re.search(r"\b\d{6}\b", t)
    if pin_match:
        idx = pin_match.start()
        start = max(0, idx - 200)
        end = min(len(t), idx + 200)
        block = t[start:end]
        india_idx = block.lower().find("india")
        if india_idx != -1:
            block = block[: india_idx + len("india")]
        return block.strip()

    for key in ["bengaluru", "bangalore"]:
        idx = low.find(key)
        if idx != -1:
            start = max(0, idx - 120)
            end = min(len(t), idx + 260)
            return t[start:end].strip()

    return None


def smart_extract_answer(question: str, text: str):
    ctx = clean_text(text)

    if is_email_question(question):
        email = extract_email(ctx)
        if email:
            return email

    if is_phone_question(question):
        phone = extract_phone(ctx)
        if phone:
            return phone

    if is_address_question(question):
        addr = extract_address_like_chunk(ctx)
        if addr:
            return f"Company Address: {addr}"

    return None
