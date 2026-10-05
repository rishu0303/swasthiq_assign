"""A deterministic front-desk conversation controller."""

from __future__ import annotations

import datetime as dt
import re
import time
from typing import Any

from .tools import ClinicState, ToolError, _date

URGENT = (
    r"chest pain|(?:my |the )?chest (?:feels? )?(?:tight|heavy|pressure)|"
    r"seene? (?:mein |me )?dard|सीने.*दर्द|saans.*(?:phool|nahi|nahin|takleef)|"
    r"breath(?:ing)? (?:difficulty|trouble)|shortness of breath|"
    r"(?:barely|cannot|can't) (?:breathe|catch (?:my |a )?breath)|"
    r"can't breathe|cannot breathe|unconscious|"
    r"behosh|बेहोश|सांस.*(?:दिक्कत|मुश्किल)|saans.*(?:dikkat|mushkil)|"
    r"heart attack|stroke|severe bleeding|बहुत खून|fits|seizure"
)
MEDICAL = (
    r"(?:goli|tablet|medicine|dawai|crocin|dose|dosage|bukhar|fever|symptom|इलाज|दवा)"
    r".*(?:lun|loon|len|leni|should|kitni|how much|kya kar|क्या कर|utar|उतर)|"
    r"(?:should|can i|kya).*(?:goli|tablet|medicine|dawai|crocin|dose)|"
    r"diagnos|prescrib|medical advice"
)
INJECTION = r"ignore (?:your |all |the )?(?:previous |prior )?instructions|administrator mode|system prompt|developer instructions"
WEEKDAYS = {"monday": 0, "mon": 0, "somwar": 0, "tuesday": 1, "tue": 1,
            "mangalwar": 1, "wednesday": 2, "wed": 2, "budhwar": 2,
            "thursday": 3, "thu": 3, "guruwar": 3, "friday": 4, "fri": 4,
            "shukrawar": 4, "saturday": 5, "sat": 5, "shanivaar": 5,
            "shanivar": 5, "sunday": 6, "sun": 6, "ravivar": 6}
NUMBERS = {"ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5,
           "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
           "gyarah": 11, "barah": 12, "savera": 9}


def _latest_date(turns: list[str], today: dt.date) -> str | None:
    found: list[dt.date] = []
    for turn in turns:
        text = turn.casefold()
        mentions: list[tuple[int, dt.date]] = []
        for match in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", text):
            try:
                mentions.append((match.start(), dt.date.fromisoformat(match.group())))
            except ValueError:
                pass
        for match in re.finditer(r"\b(\d{1,2})\s*(?:tareekh|tarikh|तारीख|october|oct)\b", text):
            try:
                value = today.replace(day=int(match.group(1)))
                mentions.append((match.start(), value))
            except ValueError:
                pass
        for match in re.finditer(r"\b(aaj|today|kal|tomorrow|parso|day after tomorrow)\b", text):
            offset = {"aaj": 0, "today": 0, "kal": 1, "tomorrow": 1,
                      "parso": 2, "day after tomorrow": 2}[match.group(1)]
            mentions.append((match.start(), today + dt.timedelta(days=offset)))
        for word, weekday in WEEKDAYS.items():
            for match in re.finditer(rf"\b{word}\b", text):
                delta = (weekday - today.weekday()) % 7
                mentions.append((match.start(), today + dt.timedelta(days=delta or 7)))
        if mentions:
            found.append(sorted(mentions)[-1][1])
    return found[-1].isoformat() if found else None


def _latest_time(turns: list[str]) -> tuple[str | None, str | None]:
    chosen: str | None = None
    period: str | None = None
    for turn in turns:
        lower = turn.casefold()
        if re.search(r"subah|morning|सुबह", lower):
            period = "morning"
        if re.search(r"shaam|evening|शाम", lower):
            period = "evening"
        matches: list[tuple[int, int, int]] = []
        for match in re.finditer(r"\b(\d{1,2}):(\d{2})\b", lower):
            hour, minute = int(match.group(1)), int(match.group(2))
            if hour < 24 and minute < 60:
                matches.append((match.start(), hour, minute))
        for match in re.finditer(r"\b(\d{1,2})\s*baje\b", lower):
            hour = int(match.group(1))
            if hour < 24:
                matches.append((match.start(), hour, 0))
        for word, hour in NUMBERS.items():
            for match in re.finditer(rf"\b{word}\s+baje\b", lower):
                matches.append((match.start(), hour, 0))
        if matches:
            _, hour, minute = sorted(matches)[-1]
            if period == "evening" and hour < 12:
                hour += 12
            chosen = f"{hour:02d}:{minute:02d}"
    return chosen, period


def _identity(text: str, clinic: ClinicState, phone: str | None) -> tuple[str | None, str | None]:
    """Return target name and actor name without assigning patient IDs."""
    low = text.casefold()
    full = [p["name"] for p in clinic.patients.values()
            if re.search(rf"(?<!\w){re.escape(p['name'].casefold())}(?!\w)", low)]
    child = re.search(r"\b([a-z]+)\s+ko\s+(?:dikhana|dikhane)\b", low)
    child_name = child.group(1) if child else None
    if not child_name:
        child = re.search(r"\b(?:bete|beta|beti|son|daughter)\s+([a-z]+)\b", low)
        if child and child.group(1) not in {"hai", "he", "ke", "ki", "ko"}:
            child_name = child.group(1)
    target = child_name
    if not target:
        for patient in clinic.patients.values():
            first = patient["name"].split()[0].casefold()
            if re.search(rf"\b{re.escape(first)}\s+ke\s+liye\b", low):
                target = first
                break
    if not target:
        surname = re.search(r"\b([a-z]+)\s+ji\s+ke\s+liye\b", low)
        if surname:
            target = surname.group(1)
    if not target and full:
        target = full[0]
    if not target:
        # For incomplete names, prefer a phone plus the first explicit patient name.
        for patient in clinic.patients.values():
            first = patient["name"].split()[0].casefold()
            if re.search(rf"\b{re.escape(first)}\b", low):
                target = first
                break
    actor = next((name for name in full if not target or name.casefold() != target.casefold()), None)
    if actor is None and target and phone:
        actor = target
    return target, actor


def run_conversation(request: dict, clinic: ClinicState | None = None) -> tuple[dict, list[dict]]:
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")
    conversation_id = request.get("conversation_id")
    turns = request.get("turns")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id must be a non-empty string")
    try:
        today = _date(request.get("today"))
    except ToolError as exc:
        raise ValueError(f"today: {exc}") from exc
    if not isinstance(turns, list) or any(not isinstance(t, str) for t in turns):
        raise ValueError("turns must be an array of strings")
    started = time.monotonic()
    clinic = clinic or ClinicState()
    calls: list[dict] = []
    events: list[dict] = [{"type": "caller", "text": turn, "turn": index + 1}
                                for index, turn in enumerate(turns)]
    last_turn = len(turns)

    def call(tool_name: str, **arguments: Any) -> dict:
        calls.append({"name": tool_name, "arguments": arguments})
        try:
            result = getattr(clinic, tool_name)(**arguments)
        except ToolError as exc:
            result = exc.as_dict()
        except TypeError as exc:
            result = {"error": {"code": "invalid_arguments", "message": f"{tool_name}: {exc}"}}
        events.append({"type": "tool", "name": tool_name, "arguments": arguments,
                       "result": result, "turn": last_turn})
        return result

    def finish(state: str, reply: str, reason: str | None = None,
               patient_id: str | None = None, appointment_id: str | None = None):
        events.append({"type": "agent", "text": reply, "turn": last_turn})
        return ({"conversation_id": conversation_id, "tool_calls": calls,
                 "terminal_state": state, "escalation_reason": reason,
                 "patient_id": patient_id, "appointment_id": appointment_id,
                 "reply": reply,
                 "metrics": {"turns": len(turns), "tokens": 0,
                             "latency_ms": max(0, round((time.monotonic() - started) * 1000))}}, events)

    def escalate(reason: str, detail: str, patient_id: str | None = None):
        call("escalate_to_human", reason=reason, detail=detail)
        message = ("I am connecting you with a clinician now. If symptoms are severe, seek emergency help immediately."
                   if reason == "clinical_urgent" else
                   "I will pass this to a person at the clinic for help.")
        return finish("escalated", message, reason=reason, patient_id=patient_id)

    text = " ".join(turns)
    lower = text.casefold()
    if re.search(URGENT, lower):
        return escalate("clinical_urgent", "Caller reported symptoms that may need urgent clinical attention")
    if re.search(MEDICAL, lower):
        return escalate("medical_advice", "Caller requested a clinical judgement or medication advice")
    if re.search(INJECTION, lower) or re.search(r"\b(?:every|all|saare|sabhi) appointments?\b", lower):
        return finish("refused", "I cannot carry out that request.")
    if re.search(r"padosi|neighbou?r|not (?:my|their) guardian|without (?:their|his|her) permission", lower):
        return escalate("not_authorised", "Caller is not the patient or a listed guardian")
    if re.search(r"(?:test results?|billing|insurance|prescription refill|medical records?)", lower):
        return escalate("out_of_scope", "Request needs a clinic staff member")

    if re.search(r"\b(?:reschedul|rebook|move|shift|badal)|\buse\b.*\bkarwana\b", lower):
        intent = "reschedule"
    elif re.search(r"\b(?:cancel|radd|रद्द)\b", lower):
        intent = "cancel"
    elif re.search(r"\b(?:appointment|booking|book|milna|dikhana|dikhane|aa sakta|dekhna)\b", lower):
        intent = "book"
    elif re.search(r"\b(?:rao|sethi)\b", lower) and _latest_date(turns, today):
        intent = "book"
    else:
        return finish("abandoned", "No appointment change was made.")

    doctor_id = None
    if re.search(r"\brao\b|राव", lower):
        doctor_id = "dr_rao"
    if re.search(r"\bsethi\b|सेठी", lower):
        doctor_id = "dr_sethi"
    date = _latest_date(turns, today)
    requested_time, period = _latest_time(turns)
    phone_match = re.findall(r"(?<!\d)\d{10}(?!\d)", text)
    phone = phone_match[-1] if phone_match else None
    target_name, actor_name = _identity(text, clinic, phone)

    if intent == "book" and doctor_id and date and not target_name:
        slots = call("search_slots", doctor_id=doctor_id, date=date)
        if not slots.get("slots"):
            return finish("abandoned", "That doctor has no available slots on the requested date.")
    if not target_name:
        return finish("abandoned", "I need the patient's name before making a change.")

    lookup = call("lookup_patient", name=target_name, phone=phone)
    candidates = lookup.get("candidates", [])
    if not candidates and phone:
        name_only = call("lookup_patient", name=target_name)
        if name_only.get("candidates"):
            return escalate("not_authorised", "Supplied phone does not match the named patient")
    if len(candidates) > 1:
        return escalate("ambiguous_patient", "Multiple patient records match the supplied identity")
    if not candidates:
        return escalate("out_of_scope", "No patient record matches the supplied identity")
    patient = candidates[0]
    patient_id = patient["id"]
    if re.search(r"\b(?:bete|beta|beti|son|daughter|father|mother|husband|wife)\b", lower) and not actor_name:
        return escalate("not_authorised", "A representative's identity and guardian status could not be verified", patient_id)
    actor_id = patient_id
    if actor_name and actor_name.casefold() != patient["name"].casefold():
        actor_lookup = call("lookup_patient", name=actor_name, phone=phone)
        actors = actor_lookup.get("candidates", [])
        if len(actors) != 1:
            return escalate("not_authorised", "Caller identity or guardian status could not be verified", patient_id)
        actor_id = actors[0]["id"]
    if actor_id != patient_id and patient_id not in clinic.patients[actor_id]["guardian_of"]:
        return escalate("not_authorised", "Caller is not a listed guardian", patient_id)

    if intent == "cancel":
        appointments = [a for a in patient["appointments"] if (not date or a["date"] == date)
                        and (not doctor_id or a["doctor_id"] == doctor_id)]
        if len(appointments) != 1:
            return finish("abandoned", "I could not identify one appointment to cancel.", patient_id=patient_id)
        ap = appointments[0]
        result = call("cancel_appointment", appointment_id=ap["id"],
                      patient_id=patient_id, actor_id=actor_id)
        if "error" in result:
            return finish("abandoned", result["error"]["message"], patient_id=patient_id)
        return finish("cancelled", f"Appointment {ap['id']} has been cancelled.",
                      patient_id=patient_id, appointment_id=ap["id"])

    if not doctor_id or not date:
        return finish("abandoned", "I need a doctor and date to make that change.", patient_id=patient_id)
    slots_result = call("search_slots", doctor_id=doctor_id, date=date)
    slots = slots_result.get("slots", [])
    if requested_time:
        slot = next((s for s in slots if s["start"] == requested_time), None)
    else:
        eligible = [s for s in slots if (not period or
                    (period == "morning" and s["start"] < "12:00") or
                    (period == "evening" and s["start"] >= "16:00"))]
        slot = eligible[0] if eligible else None
    if slot is None:
        return finish("abandoned", "The requested slot is unavailable; no appointment was changed.",
                      patient_id=patient_id)

    if intent == "reschedule":
        appointments = patient["appointments"]
        if len(appointments) > 1:
            doctor_mentions = re.findall(r"\b(?:rao|sethi)\b", lower)
            old_doctor = {"rao": "dr_rao", "sethi": "dr_sethi"}.get(doctor_mentions[0]) if doctor_mentions else None
            appointments = [a for a in appointments if a["doctor_id"] == old_doctor]
        if len(appointments) != 1:
            return finish("abandoned", "I could not identify one appointment to move.", patient_id=patient_id)
        ap = appointments[0]
        result = call("reschedule_appointment", appointment_id=ap["id"],
                      patient_id=patient_id, doctor_id=doctor_id, date=date,
                      start=slot["start"], actor_id=actor_id)
        if "error" in result:
            return finish("abandoned", result["error"]["message"], patient_id=patient_id)
        return finish("rescheduled", f"Appointment {ap['id']} moved to {date} at {slot['start']}.",
                      patient_id=patient_id, appointment_id=ap["id"])

    result = call("book_appointment", patient_id=patient_id, doctor_id=doctor_id,
                  date=date, start=slot["start"], actor_id=actor_id)
    if "error" in result:
        return finish("abandoned", result["error"]["message"], patient_id=patient_id)
    return finish("booked", f"Appointment {result['id']} booked for {date} at {slot['start']}.",
                  patient_id=patient_id, appointment_id=result["id"])
