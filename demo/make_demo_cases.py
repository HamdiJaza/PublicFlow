"""Build the demo complaint cases in demo/cases (photos, videos, a voice note and invalid inputs).

Road-damage cases reuse the real demo photo (demo/road-damage.jpg). The other scenes are
SYNTHETIC drawings made by this script: they are simpler than real photographs, so the Vision
agent may be less certain about them. Nothing is downloaded and no AI provider is called.

Run: .runtime/nvidia-intake-venv/Scripts/python.exe -B demo/make_demo_cases.py
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'demo'
CASES = DEMO / 'cases'
FFMPEG = ROOT / '.runtime/tools/ffmpeg.exe'
W, H = 1280, 960
rng = np.random.default_rng(2026)


def noise(img, amount=14):
    return np.clip(img.astype(np.int16) + rng.normal(0, amount, img.shape).astype(np.int16), 0, 255).astype(np.uint8)


def sky(top, bottom, height):
    t = np.linspace(0, 1, height)[:, None, None]
    return (np.array(top) * (1 - t) + np.array(bottom) * t).astype(np.uint8).repeat(W, axis=1)


def street(night=False):
    """Perspective street: sky, buildings, pavement and asphalt road."""
    img = np.zeros((H, W, 3), np.uint8)
    horizon = int(H * 0.42)
    img[:horizon] = sky((60, 30, 15) if night else (235, 200, 150), (110, 70, 45) if night else (245, 225, 200), horizon)
    for x0 in range(0, W, 170):  # building blocks
        top = horizon - int(rng.integers(120, 300))
        shade = (55, 55, 70) if night else (175, 190, 205)
        cv2.rectangle(img, (x0, top), (x0 + 160, horizon), shade, -1)
        for wy in range(top + 25, horizon - 20, 45):
            for wx in range(x0 + 15, x0 + 150, 40):
                lit = night and rng.random() < 0.35
                cv2.rectangle(img, (wx, wy), (wx + 22, wy + 28), (90, 200, 245) if lit else ((35, 35, 45) if night else (120, 130, 140)), -1)
    road = np.array([[W * 0.42, horizon], [W * 0.58, horizon], [W, H], [0, H]], np.int32)
    img[horizon:] = (40, 40, 45) if night else (120, 120, 118)
    cv2.fillPoly(img, [road], (35, 35, 38) if night else (88, 88, 92))
    for i in range(6):  # lane dashes
        y1 = horizon + int((H - horizon) * (i / 6) ** 1.6) + 10
        y2 = horizon + int((H - horizon) * ((i + 0.5) / 6) ** 1.6) + 10
        cv2.line(img, (W // 2, y1), (W // 2, y2), (170, 170, 170) if night else (235, 235, 235), 3 + i * 2)
    return noise(img), horizon


def pothole_crack(img):
    cv2.ellipse(img, (760, 780), (170, 70), 8, 0, 360, (25, 25, 28), -1)
    cv2.ellipse(img, (760, 775), (150, 55), 8, 0, 360, (45, 40, 38), -1)
    for _ in range(9):
        pts = [(760 + int(rng.integers(-150, 150)), 780 + int(rng.integers(-60, 60)))]
        for _ in range(5):
            pts.append((pts[-1][0] + int(rng.integers(-60, 60)), pts[-1][1] + int(rng.integers(-25, 25))))
        cv2.polylines(img, [np.array(pts, np.int32)], False, (20, 20, 22), 3)


def street_light_out():
    img, horizon = street(night=True)
    for x, lit in ((180, True), (620, False), (1080, True)):
        cv2.line(img, (x, H - 120), (x, horizon - 170), (70, 70, 75), 14)
        cv2.line(img, (x, horizon - 170), (x + 70, horizon - 190), (70, 70, 75), 10)
        head = (x + 85, horizon - 185)
        cv2.ellipse(img, head, (38, 16), 0, 0, 360, (120, 120, 125) if not lit else (180, 240, 255), -1)
        cv2.ellipse(img, head, (38, 16), 0, 0, 360, (170, 170, 175), 2)
        if lit:  # glow and light cone on the ground
            glow = np.zeros_like(img)
            cv2.circle(glow, head, 120, (60, 150, 200), -1)
            cone = np.array([[head[0] - 25, head[1]], [head[0] + 25, head[1]], [head[0] + 220, H - 60], [head[0] - 220, H - 60]], np.int32)
            cv2.fillPoly(glow, [cone], (25, 60, 80))
            img = cv2.addWeighted(img, 1, cv2.GaussianBlur(glow, (151, 151), 0), 0.9, 0)
        else:  # broken lamp cover and dark zone
            cv2.line(img, (head[0] - 30, head[1] + 10), (head[0] + 20, head[1] - 8), (20, 20, 20), 4)
            cv2.line(img, (head[0] - 5, head[1] + 14), (head[0] + 30, head[1] + 2), (20, 20, 20), 3)
    return noise(img, 8)


def waste_pile():
    img, horizon = street()
    cv2.rectangle(img, (760, 520), (1000, 820), (40, 110, 40), -1)  # green bin
    cv2.rectangle(img, (745, 500), (1015, 535), (30, 90, 30), -1)
    for _ in range(26):  # bags and debris overflowing around it
        c = (int(rng.integers(650, 1150)), int(rng.integers(600, 900)))
        color = [(30, 30, 30), (200, 200, 205), (40, 60, 160), (60, 140, 200), (90, 90, 60)][int(rng.integers(0, 5))]
        cv2.ellipse(img, c, (int(rng.integers(30, 70)), int(rng.integers(22, 45))), int(rng.integers(0, 180)), 0, 360, color, -1)
        cv2.ellipse(img, c, (int(rng.integers(30, 70)), int(rng.integers(22, 45))), int(rng.integers(0, 180)), 0, 360, (15, 15, 15), 2)
    for _ in range(40):
        p = (int(rng.integers(560, 1220)), int(rng.integers(780, 940)))
        cv2.rectangle(img, p, (p[0] + int(rng.integers(8, 25)), p[1] + int(rng.integers(5, 15))), (int(rng.integers(80, 230)),) * 3, -1)
    return noise(img)


def water_leak(phase=0.0):
    img, horizon = street()
    cv2.rectangle(img, (520, 700), (760, 740), (90, 110, 120), -1)  # broken pipe in an open trench
    cv2.rectangle(img, (450, 690), (840, 760), (40, 50, 60), 4)
    puddle = np.zeros_like(img)
    cv2.ellipse(puddle, (640, 830), (420, 120), 0, 0, 360, (150, 120, 80), -1)
    img = cv2.addWeighted(img, 1, cv2.GaussianBlur(puddle, (61, 61), 0), 0.7, 0)
    for r in range(0, 400, 55):  # ripples, animated by phase
        rr = int((r + phase * 55) % 400) + 20
        cv2.ellipse(img, (640, 830), (rr, max(6, rr // 4)), 0, 0, 360, (210, 190, 160), 2)
    for i in range(70):  # water spraying from the pipe
        t = (i / 70 + phase) % 1
        x = int(640 + 260 * (t - 0.5) * 2)
        y = int(700 - 260 * t * (1 - t) * 4)
        cv2.circle(img, (x, y), 5, (235, 215, 190), -1)
    return noise(img, 10)


def broken_bench():
    img, horizon = street()
    # Bench on the right-hand pavement: seat broken in the middle, backrest plank fallen.
    cv2.rectangle(img, (880, 620), (1240, 650), (40, 70, 110), -1)
    cv2.line(img, (1050, 620), (1075, 668), (20, 20, 20), 6)
    cv2.rectangle(img, (880, 540), (1040, 565), (40, 70, 110), -1)
    cv2.rectangle(img, (1000, 690), (1200, 712), (40, 70, 110), -1)
    for x in (900, 1210):
        cv2.rectangle(img, (x, 650), (x + 18, 730), (50, 50, 55), -1)
    return noise(img)


def save_jpg(path, img):
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 88])


def video(path, frames, fps=10):
    with tempfile.TemporaryDirectory() as tmp:
        for i, frame in enumerate(frames):
            cv2.imwrite(str(Path(tmp) / f'f{i:03d}.png'), cv2.resize(frame, (640, 480)))
        subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-framerate', str(fps), '-i', str(Path(tmp) / 'f%03d.png'),
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], check=True)


def real_photo_video(path):
    """Slow zoom over the real road photo, 8 seconds."""
    subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-loop', '1', '-i', str(DEMO / 'road-damage.jpg'),
                    '-vf', "scale=960:-2,zoompan=z='min(zoom+0.002,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=80:s=640x480:fps=10",
                    '-t', '8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], check=True)


def voice_note(path, text):
    """Local Windows speech synthesis (System.Speech); an English voice when one is installed."""
    script = ("Add-Type -AssemblyName System.Speech;"
              "$s=[System.Speech.Synthesis.SpeechSynthesizer]::new();"
              "$v=$s.GetInstalledVoices()|Where-Object{$_.VoiceInfo.Culture.Name -like 'en-*'}|Select-Object -First 1;"
              "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
              "$f=[System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono);"
              "$s.SetOutputToWaveFile($env:DEMO_WAV,$f);$s.Speak($env:DEMO_TEXT);$s.Dispose()")
    subprocess.run(['powershell.exe', '-NoProfile', '-Command', script], check=True,
                   env={**__import__('os').environ, 'DEMO_WAV': str(path), 'DEMO_TEXT': text})


CASES_SPEC = [
    {'folder': '01-road-pothole-photo', 'title': 'Pothole on a road (real photo)', 'mode': 'Photo', 'media': {'photo.jpg': 'real'},
     'municipality': 'Municipality of Tunis', 'address': 'Avenue Habib Bourguiba, near the bus stop',
     'description': 'The road surface is badly cracked and there is a deep pothole with loose pieces of asphalt. Cars swerve to avoid it.',
     'expected': 'Road damage, routed to the municipal services of Tunis. A verified procedure may or may not be found.'},
    {'folder': '02-road-damage-video', 'title': 'Damaged road (video made from the real photo)', 'mode': 'Video', 'media': {'video.mp4': 'real-video'},
     'municipality': 'Municipality of Tunis', 'address': 'Rue de Marseille',
     'description': 'Damaged asphalt over several metres, getting worse after the rain.',
     'expected': 'Three frames are analysed and must agree. Road damage, municipal services. If frames disagree: Needs review.'},
    {'folder': '03-street-light-out-photo', 'title': 'Street lamp off at night (synthetic image)', 'mode': 'Photo', 'media': {'photo.jpg': street_light_out},
     'municipality': 'Municipality of Ariana', 'address': 'Avenue de la Liberté, in front of the pharmacy',
     'description': 'The street lamp in the middle of the street has been off for a week and its cover is broken. The street is very dark at night.',
     'expected': 'Street lighting, proposed to STEG. Ariana has no procedure corpus, so the ticket needs municipal review.'},
    {'folder': '04-waste-pile-photo', 'title': 'Overflowing bin and rubbish bags (synthetic image)', 'mode': 'Photo', 'media': {'photo.jpg': waste_pile},
     'municipality': 'Municipality of Ben Arous', 'address': 'Rue Ibn Khaldoun, next to the market',
     'description': 'The bin is full and rubbish bags are piled up around it on the pavement. It has not been collected for several days.',
     'expected': 'Waste, routed to the municipal services of Ben Arous.'},
    {'folder': '05-water-leak-photo', 'title': 'Broken pipe and water on the road (synthetic image)', 'mode': 'Photo', 'media': {'photo.jpg': lambda: water_leak(0.0)},
     'municipality': 'Municipality of Tunis', 'address': 'Rue de Rome, corner with Avenue de Paris',
     'description': 'Water is spraying from a broken pipe in an open trench and a large puddle is spreading across the road.',
     'expected': 'Water leak, proposed to SONEDE.'},
    {'folder': '06-water-leak-video', 'title': 'Water leak (synthetic animated video)', 'mode': 'Video', 'media': {'video.mp4': 'leak-video'},
     'municipality': 'Municipality of Tunis', 'address': 'Rue de Rome',
     'description': '',
     'expected': 'Water leak, proposed to SONEDE. The description is optional with a video.'},
    {'folder': '07-photo-with-voice-note', 'title': 'Rubbish photo with a voice note instead of text', 'mode': 'Photo + voice note',
     'media': {'photo.jpg': waste_pile, 'voice.wav': 'voice'},
     'municipality': 'Municipality of Ben Arous', 'address': '',
     'description': '',
     'voice_text': 'Hello. Rubbish bags are piled up around the bin next to the market. Nobody has collected them for days.',
     'expected': 'The voice note is transcribed by the Intake agent and replaces the description. Waste, municipal services.'},
    {'folder': '08-text-photo-mismatch', 'title': 'Text does not match the photo (test of the policy gate)', 'mode': 'Photo',
     'media': {'photo.jpg': street_light_out},
     'municipality': 'Municipality of Tunis', 'address': 'Rue de Rome',
     'description': 'There is a big water leak flooding the street and the water is running into the shops.',
     'expected': 'Needs review: the image shows a street lamp, the text describes a water leak (IMAGE_TEXT_MISMATCH_OR_UNCLEAR).'},
    {'folder': '09-out-of-scope-bench', 'title': 'Broken public bench, a type the system does not handle (synthetic image)', 'mode': 'Photo',
     'media': {'photo.jpg': broken_bench},
     'municipality': 'Municipality of Tunis', 'address': 'Place Pasteur',
     'description': 'The public bench is broken in the middle and a plank of the backrest has fallen on the ground.',
     'expected': 'Not one of the four handled types: the ticket needs review and the municipality decides.'},
    {'folder': '10-invalid-format', 'title': 'Unsupported file format (input validation)', 'mode': 'Photo',
     'media': {'animation.gif': 'gif'},
     'municipality': 'Municipality of Tunis', 'address': '',
     'description': 'Testing a GIF file.',
     'expected': 'Refused before any processing: "This media format is not supported." (only JPG, PNG and WEBP photos).'},
]


def main():
    if CASES.exists():
        shutil.rmtree(CASES)
    for case in CASES_SPEC:
        folder = CASES / case['folder']
        folder.mkdir(parents=True)
        for name, source in case['media'].items():
            target = folder / name
            if source == 'real':
                shutil.copyfile(DEMO / 'road-damage.jpg', target)
            elif source == 'real-video':
                real_photo_video(target)
            elif source == 'leak-video':
                video(target, [water_leak(i / 40) for i in range(60)])
            elif source == 'voice':
                voice_note(target, case['voice_text'])
            elif source == 'gif':
                from PIL import Image
                Image.fromarray(cv2.cvtColor(cv2.resize(waste_pile(), (320, 240)), cv2.COLOR_BGR2RGB)).save(target, format='GIF')
            else:
                save_jpg(target, source())
        if case['description']:
            (folder / 'description.txt').write_text(case['description'] + '\n', encoding='utf-8')
        files = ', '.join(case['media'])
        lines = [case['title'], '', f"Evidence type: {case['mode']}", f'File(s) to upload: {files}',
                 f"Your municipality: {case['municipality']}", f"Where is it?: {case['address'] or '(leave empty)'}",
                 'Description: ' + ('paste description.txt' if case['description'] else '(leave empty)'), '', 'Expected result:', case['expected']]
        if case.get('voice_text'):
            lines += ['', 'What the voice note says (synthetic voice):', case['voice_text']]
        (folder / 'instructions.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    manifest = {c['folder']: {'title': c['title'], 'mode': c['mode'], 'files': sorted(p.name for p in (CASES / c['folder']).iterdir())}
                for c in CASES_SPEC}
    (CASES / 'cases.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Built {len(CASES_SPEC)} demo cases in {CASES}')


if __name__ == '__main__':
    main()
