"""JARVIS Windows desktop command center with a continuous neural-humanoid visual state engine."""
import json, math, os, queue, random, threading, tkinter as tk
from pathlib import Path
from tkinter import ttk
from agent.runtime import build_agent
from agent import tts, voice
BG="#03070d"; PANEL="#08111b"; PANEL2="#0c1925"; LINE="#183246"; CYAN="#48e6ff"; TEXT="#e9fbff"; MUTED="#6e8ca0"; GREEN="#5cffaa"; RED="#ff5f78"; GOLD="#ffd166"
APP_DIR=Path(os.environ.get("APPDATA",Path.home()))/"JARVIS"; SETTINGS_FILE=APP_DIR/"settings.json"; DEFAULT_PROVIDER="openai-compatible"; DEFAULT_URL="http://127.0.0.1:11434/v1/chat/completions"
def load_settings():
    try:return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError,ValueError):return {}
def save_settings(data):
    APP_DIR.mkdir(parents=True,exist_ok=True); SETTINGS_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
class NeuralAvatar(tk.Canvas):
    STATES={"idle":"ОЖИДАНИЕ","listening":"СЛУШАЮ","thinking":"РАССУЖДАЮ","executing":"ВЫПОЛНЯЮ","speaking":"ОТВЕЧАЮ","confirmation":"ПОДТВЕРЖДЕНИЕ","error":"ОШИБКА","exiting":"ЗАВЕРШЕНИЕ"}
    def __init__(self,master,**kw):
        super().__init__(master,bg=BG,highlightthickness=0,**kw); self.state="idle"; self.target="idle"; self.t=0; self.nodes=[]; self.links=[]; rnd=random.Random(17)
        for _ in range(95):
            a=rnd.random()*math.tau; z=rnd.uniform(-1,1); r=58*math.sqrt(max(0,1-z*z)); self.nodes.append([r*math.cos(a),r*math.sin(a)*1.18,z,rnd.random()*math.tau])
        for i in range(len(self.nodes)):
            for j in range(i+1,min(i+8,len(self.nodes))):
                dx=self.nodes[i][0]-self.nodes[j][0]; dy=self.nodes[i][1]-self.nodes[j][1]
                if dx*dx+dy*dy<950 and rnd.random()<.18:self.links.append((i,j))
        self.bind("<Configure>",lambda e:self.draw()); self.after(33,self.tick)
    def set_state(self,state):
        if state in self.STATES:self.target=state
    def tick(self):
        self.t+=.045
        if self.state!=self.target and self.t%1.0<.09:self.state=self.target
        self.draw(); self.after(33,self.tick)
    def draw(self):
        self.delete("all"); w=max(1,self.winfo_width()); h=max(1,self.winfo_height()); cx=w*.5; cy=h*.47; pulse=1+.08*math.sin(self.t*(2.0 if self.state in ("thinking","executing") else 1.1)); active=self.state in ("listening","thinking","executing","speaking")
        self.create_oval(cx-112,cy+42,cx+112,cy+245,outline="#0e2d3d",width=2); self.create_arc(cx-112,cy+42,cx+112,cy+245,200,140,style="arc",outline="#1a7186",width=2); self.create_line(cx-72,cy+85,cx-120,cy+175,fill="#14556a",width=2); self.create_line(cx+72,cy+85,cx+120,cy+175,fill="#14556a",width=2)
        for k in range(5):
            rx=(76-k*8)*pulse; ry=(96-k*9)*pulse; self.create_oval(cx-rx,cy-ry,cx+rx,cy+ry,outline="#0b3a4d" if k else "#1d7185",width=1)
        self.create_oval(cx-60,cy-78,cx+60,cy+78,outline="#2b94aa",width=2); self.create_line(cx-42,cy-2,cx-18,cy+4,fill=CYAN,width=2); self.create_line(cx+18,cy+4,cx+42,cy-2,fill=CYAN,width=2); self.create_arc(cx-28,cy+18,cx+28,cy+45,10,160,style="arc",outline=CYAN,width=2)
        pts=[]
        for x,y,z,phase in self.nodes:
            q=1/(1.25-z*.45); pts.append((cx+x*q,cy+y*q,z,phase))
        for i,j in self.links:
            x1,y1,_,_=pts[i]; x2,y2,_,_=pts[j]; strength=.35+.35*math.sin(self.t*3+pts[i][3]); self.create_line(x1,y1,x2,y2,fill="#164b5d",width=1)
            if active and strength>.55:
                u=(self.t*.7+pts[i][3])%1; self.create_oval(x1+(x2-x1)*u-2,y1+(y2-y1)*u-2,x1+(x2-x1)*u+2,y1+(y2-y1)*u+2,fill=CYAN,outline="")
        for x,y,z,phase in pts:
            s=max(1.2,3.2+2*z+1.4*math.sin(self.t*3+phase)); self.create_oval(x-s,y-s,x+s,y+s,fill=CYAN if z>.1 or active else "#55a9ba",outline="")
        core=8+5*(1+math.sin(self.t*3.2)); self.create_oval(cx-core,cy-core,cx+core,cy+core,fill=CYAN,outline=""); col=RED if self.state=="error" else GOLD if self.state=="confirmation" else CYAN
        self.create_text(cx,cy+112,text=self.STATES[self.state],fill=col,font=("Segoe UI",11,"bold")); self.create_text(cx,cy+132,text="NEURAL HUMANOID // J·A·R·V·I·S",fill=MUTED,font=("Segoe UI",8,"bold"))
class JarvisDesktop(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("JARVIS — Neural Command Center"); self.geometry("1360x820"); self.minsize(1050,680); self.configure(bg=BG); self.agent=None; self.busy=False; self.events=queue.Queue(); self.tool_names=[]; self._voice_loop_running=False; self.state="idle"; self._apply_settings(); self._style(); self._ui(); self._start_agent(); self.after(70,self._drain); self.protocol("WM_DELETE_WINDOW",self._close)
    def _apply_settings(self):
        s=load_settings(); os.environ["JARVIS_PROVIDER"]=s.get("provider") or os.environ.get("JARVIS_PROVIDER") or DEFAULT_PROVIDER; os.environ["JARVIS_CHAT_URL"]=s.get("url") or os.environ.get("JARVIS_CHAT_URL") or DEFAULT_URL
        if s.get("model") or os.environ.get("JARVIS_CHAT_MODEL"):os.environ["JARVIS_CHAT_MODEL"]=s.get("model") or os.environ["JARVIS_CHAT_MODEL"]
    def _style(self):
        st=ttk.Style(self); st.theme_use("clam"); st.configure("TButton",background=PANEL2,foreground=TEXT,bordercolor=LINE,padding=(11,9),font=("Segoe UI",10)); st.map("TButton",background=[("active","#123044")]); st.configure("Accent.TButton",background="#103b4a",foreground=CYAN,bordercolor=CYAN)
    def _ui(self):
        self.grid_columnconfigure(1,weight=1); self.grid_rowconfigure(1,weight=1); hd=tk.Frame(self,bg=BG); hd.grid(row=0,column=0,columnspan=3,sticky="ew"); hd.grid_columnconfigure(1,weight=1); tk.Label(hd,text="JARVIS",bg=BG,fg=CYAN,font=("Segoe UI",25,"bold"),padx=24).grid(row=0,column=0,pady=16); tk.Label(hd,text="NEURAL PERSONAL AI / COMMAND CENTER",bg=BG,fg=MUTED,font=("Segoe UI",9,"bold")).grid(row=0,column=1,sticky="w"); self.status=tk.Label(hd,text="● STARTING",bg=BG,fg=MUTED,font=("Segoe UI",10,"bold"),padx=24); self.status.grid(row=0,column=2,sticky="e")
        side=tk.Frame(self,bg=PANEL,highlightbackground=LINE,highlightthickness=1); side.grid(row=1,column=0,sticky="nsew",padx=(12,6),pady=(0,12)); tk.Label(side,text="СИСТЕМА",bg=PANEL,fg=MUTED,font=("Segoe UI",9,"bold"),padx=16,pady=16).pack(anchor="w")
        for text,cmd in (("◈  Система",lambda:self.send("/status")),("◉  Память",lambda:self.send("/recall")),("⌁  Инструменты",self.show_tools),("⚙  Настройки",self.show_settings)):ttk.Button(side,text=text,command=cmd).pack(fill="x",padx=10,pady=5)
        tk.Label(side,text="БЫСТРЫЕ КОМАНДЫ",bg=PANEL,fg=MUTED,font=("Segoe UI",9,"bold"),padx=16,pady=16).pack(anchor="w")
        for label,cmd in (("Статус","/status"),("Время","/now"),("Что умеешь?","Что ты умеешь?")):ttk.Button(side,text=label,command=lambda c=cmd:self.send(c)).pack(fill="x",padx=10,pady=4)
        center=tk.Frame(self,bg=BG); center.grid(row=1,column=1,sticky="nsew",padx=6,pady=(0,12)); center.grid_rowconfigure(1,weight=1); center.grid_columnconfigure(0,weight=1); self.avatar=NeuralAvatar(center,height=320); self.avatar.grid(row=0,column=0,sticky="ew",pady=(0,5)); self.hud=tk.Label(center,text="Инициализация нейросети…",bg=BG,fg=CYAN,font=("Segoe UI",11,"bold")); self.hud.grid(row=0,column=0,sticky="nw",padx=18,pady=12)
        cf=tk.Frame(center,bg=PANEL,highlightbackground=LINE,highlightthickness=1); cf.grid(row=1,column=0,sticky="nsew"); cf.grid_rowconfigure(0,weight=1); cf.grid_columnconfigure(0,weight=1); self.chat=tk.Text(cf,bg=PANEL,fg=TEXT,insertbackground=CYAN,relief="flat",wrap="word",padx=18,pady=16,font=("Segoe UI",11),state="disabled"); self.chat.grid(row=0,column=0,sticky="nsew"); sc=ttk.Scrollbar(cf,command=self.chat.yview); sc.grid(row=0,column=1,sticky="ns"); self.chat.configure(yscrollcommand=sc.set)
        inp=tk.Frame(center,bg=BG); inp.grid(row=2,column=0,sticky="ew",pady=(9,0)); inp.grid_columnconfigure(0,weight=1); self.input=tk.Entry(inp,bg=PANEL2,fg=TEXT,insertbackground=CYAN,relief="flat",font=("Segoe UI",11)); self.input.grid(row=0,column=0,sticky="ew",ipady=12,padx=(0,8)); self.input.bind("<Return>",lambda e:self.send()); self.voice_button=ttk.Button(inp,text="🎙 СЛУШАТЬ",command=self.start_voice); self.voice_button.grid(row=0,column=1,padx=(0,8)); self.send_button=ttk.Button(inp,text="ОТПРАВИТЬ",style="Accent.TButton",command=self.send); self.send_button.grid(row=0,column=2,ipadx=8)
        right=tk.Frame(self,bg=PANEL,highlightbackground=LINE,highlightthickness=1); right.grid(row=1,column=2,sticky="nsew",padx=(6,12),pady=(0,12)); tk.Label(right,text="ЖИВОЕ СОСТОЯНИЕ",bg=PANEL,fg=MUTED,font=("Segoe UI",9,"bold"),padx=16,pady=16).pack(anchor="w"); self.metrics={}
        for n in ("Core","AI Provider","Memory","Tools","Voice"):
            r=tk.Frame(right,bg=PANEL); r.pack(fill="x",padx=16,pady=7); tk.Label(r,text=n,bg=PANEL,fg=MUTED,font=("Segoe UI",9)).pack(side="left"); v=tk.Label(r,text="—",bg=PANEL,fg=CYAN,font=("Segoe UI",9,"bold")); v.pack(side="right"); self.metrics[n]=v
        tk.Label(right,text="ТЕКУЩЕЕ ДЕЙСТВИЕ",bg=PANEL,fg=MUTED,font=("Segoe UI",9,"bold"),padx=16,pady=18).pack(anchor="w"); self.action=tk.Label(right,text="Ожидание",bg=PANEL,fg=TEXT,justify="left",wraplength=220,padx=16); self.action.pack(anchor="w"); tk.Label(right,text="СОСТОЯНИЯ",bg=PANEL,fg=MUTED,font=("Segoe UI",9,"bold"),padx=16,pady=18).pack(anchor="w"); tk.Label(right,text="IDLE → LISTENING → THINKING → EXECUTING → SPEAKING\n\nCONFIRMATION / ERROR / EXITING",bg=PANEL,fg=CYAN,justify="left",wraplength=220,padx=16).pack(anchor="w")
    def _set_state(self,state,action=None):
        self.state=state; self.avatar.set_state(state); self.status.config(text="● "+state.upper(),fg=RED if state=="error" else GOLD if state=="confirmation" else GREEN if state=="idle" else CYAN); self.action.config(text=action or NeuralAvatar.STATES.get(state,state))
    def _start_agent(self):
        def work():
            try:self.events.put(("ready",build_agent()))
            except Exception as e:self.events.put(("agent_error",str(e)))
        threading.Thread(target=work,daemon=True).start()
    def _start_voice_loop(self):
        if self._voice_loop_running or not voice.available():return
        self._voice_loop_running=True; self.voice_button.config(text="🎙 СЛУШАЮ"); self._set_state("listening","Ожидаю голосовую команду")
        def work():
            while self._voice_loop_running:
                try:
                    cmd=voice.listen_for_wake_and_command()
                    if cmd:self.events.put(("voice_text",cmd))
                except Exception as e:self.events.put(("voice_error",str(e))); break
            self._voice_loop_running=False
        threading.Thread(target=work,daemon=True).start()
    def _drain(self):
        try:
            while True:
                e=self.events.get_nowait(); k=e[0]
                if k=="ready":
                    self.agent=e[1]; self.tool_names=list(self.agent.tools.names()); p=getattr(self.agent.provider,"name","unknown").upper(); self.metrics["Core"].config(text="ONLINE",fg=GREEN); self.metrics["AI Provider"].config(text=p,fg=GREEN); self.metrics["Memory"].config(text="ACTIVE",fg=GREEN); self.metrics["Tools"].config(text=str(len(self.tool_names)),fg=GREEN); ve=voice.available(); te=tts.current_engine(); self.metrics["Voice"].config(text=("STT + "+te.upper()) if ve else te.upper(),fg=GREEN if te!="off" else RED); self.hud.config(text="Нейросеть активна • "+p); self._append("JARVIS","Система готова. Нейронное ядро активно."); self._set_state("listening","Голосовой контур готов");
                    if ve:self._start_voice_loop()
                elif k=="voice_text":self.input.delete(0,"end"); self.input.insert(0,e[1]); self.send(e[1])
                elif k=="reply":
                    reply=e[1]; self._append("JARVIS",reply); self.busy=False; self.send_button.config(state="normal"); self._set_state("speaking","Формирую и озвучиваю ответ"); threading.Thread(target=self._speak,args=(reply,),daemon=True).start()
                elif k=="done_speaking":self._set_state("listening","Готов к следующей команде")
                elif k=="agent_error":self.busy=False; self.send_button.config(state="normal"); self._append("СИСТЕМА","Ошибка запуска: "+e[1]); self._set_state("error",e[1])
                elif k=="voice_error":self._append("ГОЛОС","Ошибка: "+e[1]); self._set_state("error",e[1])
                elif k=="tts_error":self._append("ГОЛОС","Ошибка TTS: "+e[1]); self._set_state("error",e[1])
        except queue.Empty:pass
        self.after(70,self._drain)
    def _speak(self,text):
        try:tts.speak_and_play(text)
        except Exception as e:self.events.put(("tts_error",str(e)))
        self.events.put(("done_speaking",))
    def _append(self,who,text):
        self.chat.configure(state="normal"); self.chat.insert("end",who+"\n","who"); self.chat.insert("end",text+"\n\n","body"); self.chat.tag_configure("who",foreground=CYAN,font=("Segoe UI",9,"bold")); self.chat.tag_configure("body",foreground=TEXT); self.chat.see("end"); self.chat.configure(state="disabled")
    def send(self,text=None):
        if text is None:text=self.input.get()
        text=text.strip()
        if not text or self.agent is None or self.busy:return
        self.input.delete(0,"end"); self._append("ВЫ",text); self.busy=True; self.send_button.config(state="disabled"); self._set_state("thinking","Анализирую запрос")
        def work():
            try:self.events.put(("reply",self.agent.handle(text).text))
            except Exception as e:self.events.put(("reply","Ошибка: "+str(e)))
        threading.Thread(target=work,daemon=True).start()
    def start_voice(self):
        if self._voice_loop_running:self._append("ГОЛОС","Режим слушания уже активен."); return
        self._start_voice_loop()
        if not self._voice_loop_running:self._append("ГОЛОС","Голосовой ввод недоступен.")
    def show_tools(self):self._append("JARVIS","Инструменты:\n"+"\n".join("• /"+n for n in self.tool_names))
    def show_settings(self):
        win=tk.Toplevel(self); win.title("JARVIS — Настройки"); win.geometry("720x350"); win.configure(bg=PANEL); win.transient(self); win.grab_set(); s=load_settings(); fields=(("Провайдер","provider",os.environ.get("JARVIS_PROVIDER",DEFAULT_PROVIDER)),("URL","url",os.environ.get("JARVIS_CHAT_URL",DEFAULT_URL)),("Модель","model",os.environ.get("JARVIS_CHAT_MODEL",s.get("model","")))); ent={}
        for i,(lab,key,val) in enumerate(fields):tk.Label(win,text=lab,bg=PANEL,fg=MUTED).grid(row=i,column=0,sticky="w",padx=20,pady=(20 if i==0 else 12)); ent[key]=tk.Entry(win,bg=PANEL2,fg=TEXT,insertbackground=CYAN,relief="flat"); ent[key].grid(row=i,column=1,sticky="ew",padx=20,pady=(20 if i==0 else 12),ipady=7); ent[key].insert(0,val)
        win.grid_columnconfigure(1,weight=1)
        def save():
            data={"provider":ent["provider"].get().strip(),"url":ent["url"].get().strip(),"model":ent["model"].get().strip()}; save_settings(data); os.environ.update({"JARVIS_PROVIDER":data["provider"],"JARVIS_CHAT_URL":data["url"],"JARVIS_CHAT_MODEL":data["model"]}); self._append("СИСТЕМА","Настройки сохранены. Перезапустите JARVIS для нового подключения."); win.destroy()
        ttk.Button(win,text="СОХРАНИТЬ",style="Accent.TButton",command=save).grid(row=4,column=1,sticky="e",padx=20,pady=20)
    def _close(self):self._set_state("exiting","Завершение JARVIS"); self._voice_loop_running=False; self.after(220,self.destroy)
if __name__=="__main__":JarvisDesktop().mainloop()
