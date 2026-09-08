# CareAnchor demo

[Watch or download the 60-second MP4](careanchor-demo.mp4) · [Narration script](transcript.md) · [Captions](captions.srt)

Recorded September 8, 2026 from the working local application. The film uses actual interface interactions and two live GPT-6-Astra requests, with a fictional resident, Alex, Morgan, and a fictional hospital. This cut has captions and no audio; narration can be recorded later. Model waiting time and pauses are shortened.

The recording shows:

1. A resident asks for Alex to drive to and from the hospital and Morgan to accompany them.
2. CareAnchor retrieves the fictional provider record and creates three separate responsibilities.
3. Each family perspective accepts its own responsibility; accepting one does not accept another.
4. The resident receives a grounded update. Attendance, paperwork preparation, and the unknown return pickup time remain separate.
5. A supplied time/location change cancels the old requests and requires new family replies.

The pitch starts with independent care-management practices as the current target-buyer hypothesis. Older adults and their families are the users and beneficiaries. Reduced coordination time, fewer missed handoffs, and greater independence are intended impacts, not measured outcomes.

This is the web rehearsal, not a recording of a native Apple Messages round trip. No private account configuration, personal Messages history, contact lists, or credentials appear in the film.

Run the application from the repository root with `python3 server.py`. Local simulation needs no model connection; live interpretation requires the signed-in compatible desktop runtime described in the main README.
