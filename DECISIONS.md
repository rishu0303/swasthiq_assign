# Decisions and ambiguities

| Ambiguity | Decision and reason |
|---|---|
| The schema example books 3 October after a 1 October request for "kal", identifies an unnamed patient, and omits `lookup_patient`. | Treat it as a JSON shape example only. `today` controls relative dates, and identity comes from `lookup_patient`. |
| The brief says two windows per doctor per day, but the JSON has one-window days. Dr. Rao's Monday windows overlap for 15 minutes. | `clinic.json` is authoritative. Merge/deduplicate generated starts before filtering bookings. |
| Each evaluation request resets, while two simultaneous bookings must not both succeed. | Give each `/agent/run` its own clinic snapshot. A `ClinicState` instance locks search and mutation and can be used by a persistent service without double booking. Independent evaluation runs can validly create the same appointment ID. |
| No appointment-lookup tool is named. | `lookup_patient` returns the patient's active appointments along with identity candidates. Cancellation and rescheduling only use IDs returned by that tool. |
| Phone numbers and names are not strong real-world authorization. | The synthetic examples use them as identity evidence. The tool layer still checks `guardian_of` for another person's record. This is a demo policy, not production authentication. |
| A caller's turns are fixed and can introduce an emergency late. | Defer every mutation until all turns have been inspected; urgent clinical language preempts the pending booking. |
| A request for a taken slot may be followed by a correction. | The latest explicit date/time correction wins. Never substitute a different exact time without the caller's consent. |
| The mockup uses September conversation data, while scripts use October. | Match its layout and content types, but show data from actual runs. |
| The brief calls the supplied material confidential but requests a public repository. | Do not copy the brief PDF into the project or publish it automatically. Seek clarification before publishing starter materials. |
| The brief permits an LLM but does not explicitly require one; no test key was supplied. | Use a deterministic rule-based conversation layer. Report model as "none" and tokens as zero. This trades broad language coverage for repeatability and offline operation; unsupported language is escalated or left unacted upon. |
| An urgent paraphrase ("chest feels tight" and "barely catch my breath") initially passed the exact-phrase safety check and booked an appointment. | Add the phrasing to the urgent matcher and a regression script (`adv_0009`). The pre-fix failure and post-fix result are shown in the video. A rule matcher remains limited, so broader reviewed triage coverage is still needed before real-world use. |
