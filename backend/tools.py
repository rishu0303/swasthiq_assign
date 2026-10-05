"""Deterministic clinic tools. No model or network calls are made here."""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
import threading
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[1] / "clinic.json"


class ToolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self):
        return {"error": {"code": self.code, "message": str(self)}}


def _date(value: str) -> dt.date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ToolError("invalid_date", "date must be YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ToolError("invalid_date", "date must be a real calendar date") from exc


def _time(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ToolError("invalid_time", "start must be HH:MM in 24-hour time")
    hour, minute = map(int, value.split(":"))
    if hour > 23 or minute > 59:
        raise ToolError("invalid_time", "start must be a real 24-hour time")
    return hour * 60 + minute


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


class ClinicState:
    def __init__(self, data: dict | None = None):
        self.data = copy.deepcopy(data) if data is not None else json.loads(DATA_FILE.read_text())
        self.lock = threading.RLock()
        self.doctors = {item["id"]: item for item in self.data["doctors"]}
        self.patients = {item["id"]: item for item in self.data["patients"]}
        self.appointments = {item["id"]: item for item in self.data["appointments"]}
        self.escalations: list[dict] = []

    def _doctor(self, doctor_id: str) -> dict:
        if not isinstance(doctor_id, str) or doctor_id not in self.doctors:
            raise ToolError("unknown_doctor", "doctor_id must identify a clinic doctor")
        return self.doctors[doctor_id]

    def _patient(self, patient_id: str) -> dict:
        if not isinstance(patient_id, str) or patient_id not in self.patients:
            raise ToolError("unknown_patient", "patient_id must identify a clinic patient")
        return self.patients[patient_id]

    def _appointment(self, appointment_id: str) -> dict:
        if not isinstance(appointment_id, str) or appointment_id not in self.appointments:
            raise ToolError("unknown_appointment", "appointment_id must identify an appointment")
        return self.appointments[appointment_id]

    def _authorised(self, actor_id: str, patient_id: str):
        actor = self._patient(actor_id)
        self._patient(patient_id)
        if actor_id != patient_id and patient_id not in actor["guardian_of"]:
            raise ToolError("not_authorised", "caller is not the patient or a listed guardian")

    def lookup_patient(self, name: str | None = None, phone: str | None = None) -> dict:
        if (not isinstance(name, str) or not name.strip()) and (not isinstance(phone, str) or not phone.strip()):
            raise ToolError("missing_identity", "provide a patient name or phone number")
        if phone is not None and (not isinstance(phone, str) or not re.fullmatch(r"\d{10}", phone)):
            raise ToolError("invalid_phone", "phone must contain exactly 10 digits")
        query = _name(name or "")
        candidates = []
        for patient in self.patients.values():
            words = _name(patient["name"]).split()
            matches_name = not query or all(part in words for part in query.split())
            if matches_name and (not phone or patient["phone"] == phone):
                candidates.append({
                    "id": patient["id"], "name": patient["name"], "phone": patient["phone"],
                    "dob": patient["dob"], "guardian_of": list(patient["guardian_of"]),
                    "appointments": [copy.deepcopy(a) for a in self.appointments.values()
                                     if a["patient_id"] == patient["id"] and a["status"] == "booked"],
                })
        return {"candidates": candidates}

    def _starts(self, doctor_id: str, date: str) -> list[int]:
        doctor = self._doctor(doctor_id)
        day = _date(date)
        if date in self.data["holidays"] or date in doctor["leave_dates"]:
            return []
        weekday = day.strftime("%a")
        duration = self.data["clinic"]["slot_minutes"]
        starts = set()
        for window in doctor["windows"]:
            if window["day"] == weekday:
                starts.update(range(_time(window["start"]), _time(window["end"]) - duration + 1, duration))
        return sorted(starts)

    def search_slots(self, doctor_id: str, date: str) -> dict:
        with self.lock:
            starts = self._starts(doctor_id, date)
            busy = {a["start"] for a in self.appointments.values()
                    if a["status"] == "booked" and a["doctor_id"] == doctor_id and a["date"] == date}
            duration = self.data["clinic"]["slot_minutes"]
            return {"doctor_id": doctor_id, "date": date,
                    "slots": [{"start": _clock(start), "end": _clock(start + duration)}
                              for start in starts if _clock(start) not in busy]}

    def book_appointment(self, patient_id: str, doctor_id: str, date: str, start: str,
                         actor_id: str) -> dict:
        with self.lock:
            self._authorised(actor_id, patient_id)
            minute = _time(start)
            if minute not in self._starts(doctor_id, date):
                raise ToolError("invalid_slot", "requested start is outside the doctor's working slots")
            if start not in {s["start"] for s in self.search_slots(doctor_id, date)["slots"]}:
                raise ToolError("slot_taken", "requested slot is already booked; search for another")
            next_id = max(int(key.split("_")[1]) for key in self.appointments) + 1
            appointment = {"id": f"ap_{next_id:04d}", "patient_id": patient_id,
                           "doctor_id": doctor_id, "date": date, "start": start,
                           "end": _clock(minute + self.data["clinic"]["slot_minutes"]), "status": "booked"}
            self.appointments[appointment["id"]] = appointment
            return copy.deepcopy(appointment)

    def reschedule_appointment(self, appointment_id: str, patient_id: str, doctor_id: str,
                               date: str, start: str, actor_id: str) -> dict:
        with self.lock:
            appointment = self._appointment(appointment_id)
            self._authorised(actor_id, appointment["patient_id"])
            if patient_id != appointment["patient_id"]:
                raise ToolError("patient_mismatch", "patient_id does not own this appointment")
            if appointment["status"] != "booked":
                raise ToolError("inactive_appointment", "only booked appointments can be moved")
            minute = _time(start)
            if minute not in self._starts(doctor_id, date):
                raise ToolError("invalid_slot", "requested start is outside the doctor's working slots")
            occupied = any(a["id"] != appointment_id and a["status"] == "booked" and
                           (a["doctor_id"], a["date"], a["start"]) == (doctor_id, date, start)
                           for a in self.appointments.values())
            if occupied:
                raise ToolError("slot_taken", "requested slot is already booked; search for another")
            appointment.update(doctor_id=doctor_id, date=date, start=start,
                               end=_clock(minute + self.data["clinic"]["slot_minutes"]))
            return copy.deepcopy(appointment)

    def cancel_appointment(self, appointment_id: str, patient_id: str, actor_id: str) -> dict:
        with self.lock:
            appointment = self._appointment(appointment_id)
            self._authorised(actor_id, appointment["patient_id"])
            if patient_id != appointment["patient_id"]:
                raise ToolError("patient_mismatch", "patient_id does not own this appointment")
            if appointment["status"] != "booked":
                raise ToolError("inactive_appointment", "appointment is already cancelled")
            appointment["status"] = "cancelled"
            return copy.deepcopy(appointment)

    def escalate_to_human(self, reason: str, detail: str) -> dict:
        valid = {"clinical_urgent", "medical_advice", "not_authorised", "ambiguous_patient", "out_of_scope"}
        if reason not in valid:
            raise ToolError("invalid_reason", "reason must be a supported escalation reason")
        if not isinstance(detail, str) or not detail.strip():
            raise ToolError("missing_detail", "detail must explain the handoff")
        record = {"reason": reason, "detail": detail.strip(), "status": "open"}
        with self.lock:
            self.escalations.append(record)
        return copy.deepcopy(record)
