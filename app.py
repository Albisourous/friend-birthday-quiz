#!/usr/bin/env python3
"""Local Kahoot-style birthday quiz server. No dependencies.

Edit QUIZ with questions about your friend. Drop question photos in img/.

Run:  python3 app.py
Host: open the URL printed in the terminal on your laptop.
Players: same Wi-Fi, open the player URL, enter a name.
"""

import json, random, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# QUIZ format: ("question text", ["correct answer", "wrong 1", "wrong 2", "wrong 3"], 0)
# Optional 4th element: an image filename in img/ shown with the question.
# The correct answer is always index 0 -- options are shuffled before display.
# Keep all options similar in length and format so the correct one doesn't stand out.
QUIZ = [
    ("What is [NAME]'s favorite food?", ["Sushi", "Pizza", "Tacos", "Pasta"], 0),
    ("Where did [NAME] grow up?", ["Portland", "Denver", "Austin", "Chicago"], 0),
    ("What is [NAME]'s job title?", ["Analyst", "Designer", "Engineer", "Manager"], 0),
    ("What is [NAME]'s favorite movie?", ["Spirited Away", "The Matrix", "Jurassic Park", "Toy Story"], 0),
    ("What is [NAME]'s biggest fear?", ["Spiders", "Heights", "Clowns", "Flying"], 0),
    ("What was [NAME]'s first job?", ["Tutor", "Barista", "Lifeguard", "Cashier"], 0),
    ("How does [NAME] take their coffee?", ["Black", "With oat milk", "Iced only", "No coffee at all"], 0),
    ("What is [NAME] doing in this photo?", ["Posing", "Jumping", "Sleeping", "Dancing"], 0),
]



QUESTION_SECONDS = 20
REVEAL_SECONDS = 7  # auto-advance to next question after reveal
SHAPES = ["\u25b2", "\u25c6", "\u25cf", "\u25a0"]  # triangle, diamond, circle, square
COLORS = ["#e21b3c", "#1368ce", "#d89e00", "#26890c"]

# No access control: intended for trusted LAN use with friends.


class Game:
    def __init__(self):
        self.lock = threading.Lock()
        self.phase = "lobby"          # lobby | intro | question | reveal | final
        self.intro_end = 0.0
        self.players = {}             # name -> {score, answered, choice, correct, gained}
        self.q_index = -1
        self.answers = []             # per-question display order (shuffled)
        self.q_start = 0.0
        self.q_end = 0.0
        self.reveal_end = 0.0
        self.q_img = None

    def snapshot(self, player=None):
        """State dict for the given viewer."""
        lb = sorted(self.players.items(), key=lambda kv: -kv[1]["score"])
        s = {
            "phase": self.phase,
            "players": [n for n, _ in lb],
            "scores": {n: p["score"] for n, p in self.players.items()},
            "q_index": self.q_index,
            "q_total": len(QUIZ),
        }
        if self.phase == "intro":
            nxt = self.q_index + 1
            s["question"] = QUIZ[nxt][0] if nxt < len(QUIZ) else ""
            s["img"] = QUIZ[nxt][3] if nxt < len(QUIZ) and len(QUIZ[nxt]) > 3 else None
            s["remaining"] = max(0, round(self.intro_end - time.time(), 1))
        elif self.phase == "question":
            s["question"] = QUIZ[self.q_index][0]
            s["answers"] = self.answers
            s["img"] = self.q_img
            s["remaining"] = max(0, round(self.q_end - time.time(), 1))
            s["answer_count"] = sum(1 for p in self.players.values() if p.get("answered"))
        elif self.phase == "reveal":
            s["question"] = QUIZ[self.q_index][0]
            s["answers"] = self.answers
            s["correct"] = QUIZ[self.q_index][2]
            s["img"] = self.q_img
            s["dist"] = [sum(1 for p in self.players.values() if p.get("choice") == i) for i in range(4)]
        if player and player in self.players:
            p = self.players[player]
            s["me"] = {
                "answered": p.get("answered", False),
                "correct": p.get("correct", False),
                "gained": p.get("gained", 0),
                "score": p["score"],
                "streak": p.get("streak", 0),
                "streak_bonus": p.get("streak_bonus", 0),
                "rank": [n for n, _ in lb].index(player) + 1,
            }
        return s


G = Game()


def start_question():
    G.q_index += 1
    if G.q_index >= len(QUIZ):
        G.phase = "final"
        return
    entry = QUIZ[G.q_index]
    q, ans, correct = entry[:3]
    G.q_img = entry[3] if len(entry) > 3 else None
    order = list(range(4))
    random.shuffle(order)
    # answers[i] = display answer i; find display index of the true answer
    G.answers = [ans[j] for j in order]
    G.display_correct = order.index(correct)
    G.phase = "question"
    G.q_start = time.time()
    G.q_end = G.q_start + QUESTION_SECONDS
    for p in G.players.values():
        p.update(answered=False, choice=None, correct=False, gained=0, streak_bonus=0)


def reveal():
    if G.phase == "question":
        G.phase = "reveal"
        G.reveal_end = time.time() + REVEAL_SECONDS


PLAYER_HTML = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>Birthday Quiz</title><style>
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:linear-gradient(160deg,#46178f,#25076b);color:#fff;text-align:center;padding:1rem}
h1{font-size:clamp(1.1rem,4.5vw,1.6rem);margin:.6rem .3rem;font-weight:800}
.big{font-size:1.5rem;font-weight:800;margin:.6rem}
.card{background:#fff1;border:1px solid #fff3;border-radius:20px;padding:1.4rem 1.8rem;backdrop-filter:blur(6px);max-width:26rem;width:100%;box-shadow:0 12px 40px #0005}
input{font-size:1.25rem;padding:.85rem 1rem;border-radius:12px;border:0;width:100%;max-width:18rem;text-align:center;font-weight:700;outline:none}
input:focus{box-shadow:0 0 0 4px #ffffff40}
.btn{font-size:1.15rem;padding:.85rem 2.2rem;border-radius:12px;border:0;background:#26890c;color:#fff;font-weight:800;cursor:pointer;margin-top:.9rem;box-shadow:0 4px 0 #1a5f09}
.btn:active{transform:translateY(3px);box-shadow:none}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem;padding:1rem;width:100%;max-width:34rem}
.grid button{min-height:6rem;font-size:1.35rem;font-weight:800;color:#fff;border:0;border-radius:14px;cursor:pointer;word-break:break-word;box-shadow:0 5px 0 #0006;text-shadow:0 1px 3px #0008;transition:transform .06s}
.grid button:active{transform:translateY(4px);box-shadow:0 1px 0 #0006}
#timer{font-size:2.8rem;font-weight:900;background:#fff2;border-radius:50%;width:4.5rem;height:4.5rem;line-height:4.5rem;margin-bottom:.4rem}
.qimg{max-width:min(88vw,20rem);max-height:38vh;border-radius:14px;margin:.4rem;box-shadow:0 8px 30px #0007}
.score{background:#fff1;border-radius:14px;padding:1rem 1.6rem;font-size:1.2rem;font-weight:700;margin-top:.8rem}
.medal{font-size:1.5rem;font-weight:800;padding:.35rem}
@keyframes pop{0%{transform:scale(.5);opacity:0}80%{transform:scale(1.08)}100%{transform:scale(1)}}
@keyframes fall{to{transform:translateY(115vh) rotate(360deg)}}
.pop{animation:pop .35s ease-out}
</style></head><body><div id=app style=width:100%;display:flex;flex-direction:column;align-items:center></div><script>
const app=document.getElementById('app');let name=localStorage.wqname||'',me={};
const SHAPES=['\\u25b2','\\u25c6','\\u25cf','\\u25a0'],COLORS=['#e21b3c','#1368ce','#d89e00','#26890c'];
function post(u,d){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(r=>r.json())}
function join(){name=document.getElementById('n').value.trim();if(!name)return;
 post('/api/join',{name}).then(r=>{console.log('join resp',r);if(r.ok){localStorage.wqname=name;poll()}else{app.innerHTML='<div class=card><h1>'+r.error+'</h1><button class=btn onclick=location.reload()>Back</button></div>'}}).catch(e=>{console.log('join failed',e);app.innerHTML='<div class=card><h1>Cannot reach server</h1><div>'+e+'</div><button class=btn onclick=location.reload()>Retry</button></div>'})}
function draw(s){me=s.me||{};
 if(s.phase==='lobby'){lastReveal=-1;confDone=0;app.innerHTML='<div class=card pop><div style=font-size:3rem>\\ud83c\\udfae</div><div class=big>You\\'re in, '+name+'!</div><div>Waiting for host to start\\u2026</div><div style=margin-top:.6rem;opacity:.7>'+s.players.length+' players in lobby</div></div>'}
 else if(s.phase==='intro'){app.innerHTML='<div class=card pop><div class=big>Get ready!</div><h1>Question '+(s.q_index+2)+' / '+s.q_total+'</h1>'+(s.img?'<img class=qimg src="/img/'+s.img+'">':'')+'</div>'}
 else if(s.phase==='question'){if(me.answered){app.innerHTML='<div id=timer>'+Math.ceil(s.remaining)+'</div><h1>'+s.question+'</h1><div class=card><div style=font-size:2.5rem>\\u23f3</div><div class=big>Answer locked in!</div></div>'}
  else{app.innerHTML='<div id=timer>'+Math.ceil(s.remaining)+'</div><h1>'+s.question+'</h1>'+(s.img?'<img class=qimg src="/img/'+s.img+'">':'')+'<div class=grid>'+s.answers.map((a,i)=>'<button style=background:'+COLORS[i]+' onclick="ans('+i+')">'+SHAPES[i]+' '+a+'</button>').join('')+'</div>'}}
 else if(s.phase==='reveal'){if(s.q_index!==lastReveal){lastReveal=s.q_index;me.correct?ding():buzz()}app.innerHTML=me.correct?'<div class=card pop><div style=font-size:3rem>\\u2705</div><div class=big>Correct! +'+me.gained+'</div>'+(me.streak>1?'<div class=medal>\\ud83d\\udd25 '+me.streak+' in a row! +'+me.streak_bonus+' bonus</div>':'')+'<div class=score>Score '+me.score+' \\u00b7 rank #'+me.rank+'</div></div>':'<div class=card pop><div style=font-size:3rem>\\u274c</div><div class=big>Wrong!</div><div class=score>Score '+me.score+' \\u00b7 rank #'+me.rank+'</div></div>'}
 else if(s.phase==='final'){if(!confDone){confDone=1;confetti()}const lb=s.players.slice(0,3);app.innerHTML='<div class=card pop><div style=font-size:3rem>\\ud83c\\udfc6</div><div class=big>Final score: '+me.score+'</div><div>Rank #'+me.rank+'</div>'+(me.rank<=3?'<div class=medal>You made the podium!</div>':'')+'</div>'+lb.map((n,i)=>'<div class=medal>'+['\\ud83e\\udd47','\\ud83e\\udd48','\\ud83e\\udd49'][i]+' '+n+' \\u2014 '+s.scores[n]+'</div>').join('')}}
function ans(i){post('/api/answer',{name,choice:i}).then(r=>{if(r.ok)poll()})}
let AC,lastReveal=-1,confDone=0;
function tone(f,d,t){try{AC=AC||new(window.AudioContext||window.webkitAudioContext)();const o=AC.createOscillator(),g=AC.createGain();o.type='square';o.frequency.value=f;o.connect(g);g.connect(AC.destination);g.gain.setValueAtTime(.15,AC.currentTime+(t||0));g.gain.exponentialRampToValueAtTime(.001,AC.currentTime+(t||0)+d);o.start(AC.currentTime+(t||0));o.stop(AC.currentTime+(t||0)+d)}catch(e){}}
function ding(){tone(523,.12);tone(784,.15,.1);tone(1047,.2,.2)}
function buzz(){tone(150,.3);tone(120,.3,.15)}
function confetti(){for(let i=0;i<40;i++){const e=document.createElement('span');e.textContent=['\\ud83c\\udf89','\\ud83c\\udf8a','\\u2b50'][i%3];e.style.cssText='position:fixed;top:-40px;left:'+Math.random()*100+'vw;font-size:1.6rem;animation:fall '+(2+Math.random()*2)+'s '+(Math.random()*2)+'s linear forwards;z-index:99';document.body.appendChild(e);setTimeout(function(x){x.remove()},6500,e)}}
function poll(){if(!name)return;fetch('/api/state?player='+encodeURIComponent(name)).then(r=>r.json()).then(draw).catch(e=>{console.log('poll failed',e)})}
if(name)post('/api/join',{name}).then(r=>{console.log('rejoin resp',r);if(r.ok)poll();else{name='';localStorage.wqname='';location.reload()}}).catch(e=>{console.log('rejoin failed',e);app.innerHTML='<div class=card><h1>Cannot reach server</h1><button class=btn onclick=location.reload()>Retry</button></div>'});else app.innerHTML='<div class=card><h1>THE BIRTHDAY QUIZ</h1><input id=n placeholder="Nickname" maxlength=16><br><button class=btn onclick=join()>Join</button></div>';
setInterval(function(){if(name)poll()},500);</script></body></html>"""

HOST_HTML = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>Quiz Host</title><style>
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;margin:0;min-height:100vh;background:linear-gradient(160deg,#46178f,#25076b);color:#fff;padding:2rem;text-align:center}
h1{margin:.4rem 0;font-size:clamp(1.3rem,3.5vw,2rem);font-weight:900}
.big{font-size:clamp(1.5rem,4vw,2.4rem);font-weight:900;margin:.8rem auto;max-width:60rem}
button{font-size:1.2rem;padding:.8rem 2rem;border-radius:12px;border:0;background:#26890c;color:#fff;font-weight:800;cursor:pointer;margin:.8rem .4rem 0;box-shadow:0 4px 0 #1a5f09}
button:active{transform:translateY(3px);box-shadow:none}
.chip{display:inline-block;background:#fff2;border:1px solid #fff3;padding:.45rem 1.1rem;border-radius:20px;margin:.25rem;font-weight:700}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;max-width:60rem;margin:1rem auto}
.card{border-radius:14px;padding:1rem;font-weight:800;font-size:1.2rem;color:#fff;box-shadow:0 4px 0 #0005}
.card.win{outline:4px solid #ffd700}
table{margin:0 auto;border-collapse:collapse;min-width:20rem}
td{padding:.45rem 1.2rem;font-weight:700;font-size:1.15rem}
tr:nth-child(odd){background:#ffffff12}
.bar{height:1.2rem;background:#ffd700;border-radius:6px;margin-top:.35rem}
.joinurl{font-size:1.4rem;font-weight:900;background:#fff;color:#46178f;display:inline-block;padding:.6rem 1.4rem;border-radius:12px;margin:.6rem}
.dim{opacity:.7}
.minor{background:#ffffff22;box-shadow:none;font-size:.9rem;padding:.5rem 1rem;position:fixed;bottom:1rem;right:1rem}
.podium{display:flex;align-items:flex-end;justify-content:center;gap:.8rem;margin:1.5rem auto}
.ped{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;width:9rem}
.pname{font-weight:800;margin-bottom:.4rem;font-size:1.1rem}
.pscore{opacity:.8;margin-bottom:.4rem}
.block{border-radius:10px 10px 0 0;width:100%;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:900;color:#0008;box-shadow:0 6px 20px #0006}
.qimg{max-width:min(70vw,26rem);max-height:42vh;border-radius:14px;margin:.4rem;box-shadow:0 8px 30px #0007}
</style></head><body><div id=app>Loading&hellip;</div><script>
const app=document.getElementById('app');
const SHAPES=['\\u25b2','\\u25c6','\\u25cf','\\u25a0'],COLORS=['#e21b3c','#1368ce','#d89e00','#26890c'];
function post(u,d){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})}).then(r=>r.json())}
function kick(n){post('/api/kick',{name:n}).then(poll)}
function draw(s){
 if(s.phase==='lobby'){app.innerHTML='<h1>\\ud83c\\udfae Birthday Quiz</h1><div class=dim>Players join at:</div><div class=joinurl>'+location.origin+'</div><div><img src="https://api.qrserver.com/v1/create-qr-code/?size=240x240&color=fff&bgcolor=46178f&data='+encodeURIComponent(location.origin+'/')+'" onerror="this.remove()" style="border-radius:14px;margin:.6rem"></div><h1>'+s.players.length+' players in lobby</h1><div>'+s.players.map(n=>'<span class=chip>'+n+' <a data-n="'+encodeURIComponent(n)+'" onclick="kick(decodeURIComponent(this.dataset.n))" style=color:#ff9;cursor:pointer>\\u2715</a></span>').join('')+'</div><br><button onclick="post(\\'/api/start\\').then(poll)">Start game</button><button onclick="post(\\'/api/clear\\').then(poll)" style=background:#e21b3c;box-shadow:0 4px 0 #8f1025>Clear players</button>'}
 else if(s.phase==='intro'){app.innerHTML='<h1>Get ready\\u2026</h1><h1>Question '+(s.q_index+2)+' / '+s.q_total+'</h1><div class=big>'+s.question+'</div>'+(s.img?'<img class=qimg src="/img/'+s.img+'">':'')}
 else if(s.phase==='question'){app.innerHTML='<h1>Question '+(s.q_index+1)+' / '+s.q_total+' \\u00b7 '+Math.ceil(s.remaining)+'s \\u00b7 '+s.answer_count+'/'+s.players.length+' answered</h1><div class=big>'+s.question+'</div>'+(s.img?'<img class=qimg src="/img/'+s.img+'">':'')+'<div class=cards>'+s.answers.map((a,i)=>'<div class=card style=background:'+COLORS[i]+'>'+SHAPES[i]+' '+a+'</div>').join('')+'</div><button onclick="post(\\'/api/reveal\\').then(poll)">Reveal now</button>'+rstbtn()}
 else if(s.phase==='reveal'){const mx=Math.max(1,...s.dist);app.innerHTML='<h1>Question '+(s.q_index+1)+' / '+s.q_total+'</h1><div class=big>'+s.question+'</div>'+(s.img?'<img class=qimg src="/img/'+s.img+'">':'')+'<div class=cards>'+s.answers.map((a,i)=>'<div class="card'+(i===s.correct?' win':'')+'" style="background:'+COLORS[i]+';'+(i===s.correct?'':'opacity:.55')+'">'+SHAPES[i]+' '+a+'<div class=bar style=width:'+Math.round(100*s.dist[i]/mx)+'%></div><div class=dim>'+s.dist[i]+' votes</div></div>').join('')+'</div><h1>Leaderboard</h1><table>'+s.players.slice(0,10).map((n,i)=>'<tr><td>'+(i+1)+'</td><td>'+n+'</td><td>'+s.scores[n]+'</td></tr>').join('')+'</table><br><button onclick="post(\\'/api/next\\').then(poll)">'+(s.q_index+1<s.q_total?'Next question':'Final results')+'</button>'+rstbtn()}
 else if(s.phase==='final'){const pc=['#ffd700','#c0c0c0','#cd7f32'],ph=[130,90,70],po=[1,0,2];app.innerHTML='<h1>\\ud83c\\udfc6 Final Results</h1><div class=podium>'+po.filter(i=>s.players[i]).map(r=>'<div class=ped><div class=pname>'+s.players[r]+'</div><div class=pscore>'+s.scores[s.players[r]]+'</div><div class=block style="height:'+ph[r]+'px;background:'+pc[r]+'">'+(r+1)+'</div></div>').join('')+'</div><table>'+s.players.map((n,i)=>'<tr><td>'+(i+1)+'. '+(['\\ud83e\\udd47','\\ud83e\\udd48','\\ud83e\\udd49'][i]||'')+' '+n+'</td><td>'+s.scores[n]+'</td></tr>').join('')+'</table><button onclick="post(\\'/api/reset\\').then(poll)">Play again</button>'+rstbtn()}
}
function rstbtn(){return '<button class=minor onclick="post(\\'/api/clear\\').then(poll)">\\u21ba Restart (clear all)</button>'}
function poll(){fetch('/api/state').then(r=>r.json()).then(draw).catch(()=>{app.innerHTML='Connection lost\\u2026'})}
poll();setInterval(poll,500);</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="text/html", code=200):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj), "application/json", code)


    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/img/"):
            import os
            name = os.path.basename(path)
            fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img", name)
            if os.path.isfile(fpath):
                data = open(fpath, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
        elif path == "/":
            self._send(PLAYER_HTML)
        elif path == "/host":
            self._send(HOST_HTML)
        elif path == "/api/state":
            player = parse_qs(urlparse(self.path).query).get("player", [None])[0]
            with G.lock:
                if G.phase == "intro" and time.time() > G.intro_end:
                    start_question()
                if G.phase == "question" and time.time() > G.q_end:
                    reveal()
                if G.phase == "reveal" and time.time() > G.reveal_end:
                    if G.q_index + 1 >= len(QUIZ):
                        G.phase = "final"
                    else:
                        G.phase = "intro"
                        G.intro_end = time.time() + 3
                s = G.snapshot(player)
                if s.get("correct") is not None:
                    s["correct"] = G.display_correct
            self._json(s)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except Exception:
            body = {}

        if path == "/api/join":
            name = str(body.get("name", "")).strip()[:16]
            if not name:
                return self._json({"ok": False, "error": "Enter a name"})
            with G.lock:
                if name not in G.players:
                    G.players[name] = {"score": 0, "answered": False, "choice": None, "correct": False, "gained": 0}
            self._json({"ok": True})

        elif path == "/api/answer":
            name = str(body.get("name", ""))
            choice = body.get("choice")
            with G.lock:
                p = G.players.get(name)
                if not p or G.phase != "question" or p.get("answered"):
                    return self._json({"ok": False})
                if time.time() > G.q_end:
                    reveal()
                    return self._json({"ok": False})
                p["answered"] = True
                p["choice"] = choice
                p["correct"] = (choice == G.display_correct)
                if p["correct"]:
                    frac = max(0.0, (G.q_end - time.time()) / QUESTION_SECONDS)
                    p["streak"] = p.get("streak", 0) + 1
                    p["streak_bonus"] = min(500, 100 * p["streak"])
                    p["gained"] = 500 + round(500 * frac) + p["streak_bonus"]
                    p["score"] += p["gained"]
                else:
                    p["streak"] = 0
                    p["streak_bonus"] = 0
                if all(pl.get("answered") for pl in G.players.values()):
                    reveal()
            self._json({"ok": True})

        elif path == "/api/kick":
            name = str(body.get("name", ""))
            with G.lock:
                G.players.pop(name, None)
            self._json({"ok": True})

        elif path in ("/api/start", "/api/reveal", "/api/next", "/api/reset", "/api/clear"):
            with G.lock:
                if path == "/api/start" and G.phase == "lobby" and G.players:
                    random.shuffle(QUIZ)
                    G.q_index = -1
                    G.phase = "intro"
                    G.intro_end = time.time() + 3
                elif path == "/api/reveal":
                    reveal()
                elif path == "/api/next" and G.phase == "reveal":
                    if G.q_index + 1 >= len(QUIZ):
                        G.phase = "final"
                    else:
                        G.phase = "intro"
                        G.intro_end = time.time() + 3
                elif path == "/api/reset":
                    G.phase = "lobby"
                    G.q_index = -1
                    for p in G.players.values():
                        p.update(score=0, answered=False, choice=None, correct=False, gained=0)
                elif path == "/api/clear":
                    G.phase = "lobby"
                    G.q_index = -1
                    G.players.clear()
            self._json({"ok": True})
        else:
            self.send_error(404)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        s.close()


if __name__ == "__main__":
    port = 8080
    ip = lan_ip()
    print(f"Host page : http://{ip}:{port}/host")
    print(f"Players   : http://{ip}:{port}/")
    print(f"(Players must be on the same Wi-Fi. Ctrl+C to stop.)")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
