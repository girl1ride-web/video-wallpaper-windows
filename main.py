import os,sys,json,ctypes,hashlib,subprocess,winreg
from ctypes import wintypes
from pathlib import Path
os.environ.setdefault("QT_MEDIA_BACKEND","ffmpeg")
os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES","d3d11va")
from PySide6.QtCore import Qt,QUrl,QTimer,QThread,Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import *
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
import imageio_ffmpeg

APP="VideoWallpaper"
DATA=Path(os.getenv("LOCALAPPDATA",str(Path.home())))/APP
CACHE=DATA/"cache"; CACHE.mkdir(parents=True,exist_ok=True)
CFG=DATA/"config.json"
u=ctypes.windll.user32
ENUM=ctypes.WINFUNCTYPE(ctypes.c_bool,wintypes.HWND,wintypes.LPARAM)
PROFILES={
"720p Ultra Eco — 15 FPS":(1280,720,15,29),
"720p Eco — 20 FPS":(1280,720,20,28),
"1080p Ultra Eco — 15 FPS":(1920,1080,15,29),
"1080p Eco — 20 FPS":(1920,1080,20,28),
"1080p Smooth — 24 FPS":(1920,1080,24,27),
"4K Ultra Eco — 15 FPS":(3840,2160,15,31),
"4K Eco — 20 FPS":(3840,2160,20,30),
"4K Smooth — 24 FPS":(3840,2160,24,29)}
DEFAULT="720p Eco — 20 FPS"

def worker():
    p=u.FindWindowW("Progman",None)
    if p:
        r=wintypes.DWORD()
        u.SendMessageTimeoutW(p,0x052C,0,0,0,1000,ctypes.byref(r))
    out=None
    @ENUM
    def cb(h,l):
        nonlocal out
        if u.FindWindowExW(h,0,"SHELLDLL_DefView",None):
            x=u.FindWindowExW(0,h,"WorkerW",None)
            if x: out=x; return False
        return True
    u.EnumWindows(cb,0)
    return out or u.FindWindowExW(0,0,"WorkerW",None)

def wsize(w):
    r=wintypes.RECT()
    if u.GetClientRect(w,ctypes.byref(r)): return max(1,r.right),max(1,r.bottom)
    return u.GetSystemMetrics(78),u.GetSystemMetrics(79)

def full():
    h=u.GetForegroundWindow()
    if not h:return False
    c=ctypes.create_unicode_buffer(256);u.GetClassNameW(h,c,256)
    if c.value in ("Progman","WorkerW","Shell_TrayWnd"):return False
    r=wintypes.RECT()
    if not u.GetWindowRect(h,ctypes.byref(r)):return False
    m=u.MonitorFromWindow(h,2)
    class MI(ctypes.Structure):
        _fields_=[("cbSize",wintypes.DWORD),("rcMonitor",wintypes.RECT),("rcWork",wintypes.RECT),("dwFlags",wintypes.DWORD)]
    i=MI();i.cbSize=ctypes.sizeof(i)
    if not u.GetMonitorInfoW(m,ctypes.byref(i)):return False
    t=3
    return r.left<=i.rcMonitor.left+t and r.top<=i.rcMonitor.top+t and r.right>=i.rcMonitor.right-t and r.bottom>=i.rcMonitor.bottom-t

def startup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k,APP);return True
    except:return False

def setstartup(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\Microsoft\Windows\CurrentVersion\Run",0,winreg.KEY_SET_VALUE) as k:
        if on:
            cmd=f'"{sys.executable}" --autostart' if getattr(sys,"frozen",False) else f'"{sys.executable}" "{Path(__file__).resolve()}" --autostart'
            winreg.SetValueEx(k,APP,0,winreg.REG_SZ,cmd)
        else:
            try:winreg.DeleteValue(k,APP)
            except FileNotFoundError:pass

def cache(src,prof):
    p=Path(src);s=p.stat();k=f"{p.resolve()}|{s.st_size}|{s.st_mtime_ns}|{prof}|production"
    return CACHE/(hashlib.sha1(k.encode()).hexdigest()[:24]+".mp4")

class Enc(QThread):
    done=Signal(str,str);fail=Signal(str);status=Signal(str)
    def __init__(self,s,d,p):super().__init__();self.s=s;self.d=str(d);self.p=p
    def run(self):
        try:
            w,h,fps,crf=PROFILES[self.p]
            vf=f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=fast_bilinear,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps}"
            cmd=[imageio_ffmpeg.get_ffmpeg_exe(),"-y","-hide_banner","-loglevel","error","-i",self.s,"-map_metadata","-1","-an","-vf",vf,"-c:v","libx264","-preset","veryfast","-tune","fastdecode","-profile:v","main","-bf","0","-refs","1","-g",str(fps*2),"-crf",str(crf),"-pix_fmt","yuv420p","-movflags","+faststart",self.d]
            self.status.emit(f"Đang tạo proxy {w}×{h} / {fps} FPS...")
            r=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,creationflags=0x08000000)
            if r.returncode:raise RuntimeError(r.stderr[-2500:])
            self.done.emit(self.d,self.p)
        except Exception as e:self.fail.emit(str(e))

class Wall(QWidget):
    def __init__(self):
        super().__init__();self.setWindowFlags(Qt.FramelessWindowHint|Qt.Tool);self.setAttribute(Qt.WA_NativeWindow,True)
        l=QVBoxLayout(self);l.setContentsMargins(0,0,0,0)
        self.v=QVideoWidget();self.v.setAspectRatioMode(Qt.KeepAspectRatioByExpanding);l.addWidget(self.v)
        self.p=QMediaPlayer(self);self.p.setVideoOutput(self.v);self.p.mediaStatusChanged.connect(self.loop)
    def loop(self,s):
        if s==QMediaPlayer.EndOfMedia:self.p.setPosition(0);self.p.play()
    def attach(self):
        self.show();h=int(self.winId());w=worker()
        if not w:return False
        u.SetParent(h,w);st=u.GetWindowLongW(h,-16);u.SetWindowLongW(h,-16,st|0x40000000|0x10000000)
        x,y=wsize(w);u.SetWindowPos(h,0,0,0,x,y,0x0040|0x0010);self.resize(x,y);self.v.setGeometry(self.rect())
        QTimer.singleShot(300,self.sync);return True
    def sync(self):
        w=worker()
        if w:
            x,y=wsize(w);u.MoveWindow(int(self.winId()),0,0,x,y,True);self.resize(x,y);self.v.setGeometry(self.rect())
    def play(self,f):
        if not self.attach():raise RuntimeError("Không gắn được wallpaper vào WorkerW")
        self.p.stop();self.p.setSource(QUrl.fromLocalFile(f));self.p.play()
    def stop(self):self.p.stop();self.hide()
    def resizeEvent(self,e):super().resizeEvent(e);self.v.setGeometry(self.rect())

class Main(QMainWindow):
    def __init__(self,auto=False):
        super().__init__();self.wall=Wall();self.src="";self.proxy="";self.active="";self.enc=None;self.quitflag=False;self.ap=False
        self.setWindowTitle("Video Wallpaper");self.resize(670,440)
        c=QWidget();self.setCentralWidget(c);l=QVBoxLayout(c)
        t=QLabel("VIDEO WALLPAPER");t.setStyleSheet("font-size:22px;font-weight:700");l.addWidget(t)
        
        self.fl=QLabel("Chưa chọn video");self.fl.setWordWrap(True);l.addWidget(self.fl)
        r=QHBoxLayout();r.addWidget(QLabel("Chế độ:"));self.cb=QComboBox();self.cb.addItems(PROFILES);self.cb.setCurrentText(DEFAULT);self.cb.currentTextChanged.connect(self.changed);r.addWidget(self.cb);l.addLayout(r)
        self.fs=QCheckBox("Tạm dừng khi game/app fullscreen");self.fs.setChecked(True);l.addWidget(self.fs)
        r=QHBoxLayout();self.pick=QPushButton("Chọn video");self.pp=QPushButton("Play / Pause");self.st=QPushButton("Dừng");r.addWidget(self.pick);r.addWidget(self.pp);r.addWidget(self.st);l.addLayout(r)
        self.su=QPushButton();l.addWidget(self.su);self.bar=QProgressBar();self.bar.setRange(0,0);self.bar.hide();l.addWidget(self.bar);self.status=QLabel("Sẵn sàng");l.addWidget(self.status)
        self.pick.clicked.connect(self.choose);self.pp.clicked.connect(self.toggle);self.st.clicked.connect(self.stop);self.su.clicked.connect(self.togsu)
        self.tray=QSystemTrayIcon(self);self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon));m=QMenu()
        for name,fn in [("Mở",self.showagain),("Play / Pause",self.toggle),("Dừng",self.stop),("Thoát hoàn toàn",self.exit)]:
            a=QAction(name,self);a.triggered.connect(fn);m.addAction(a)
        self.tray.setContextMenu(m);self.tray.show();self.load();self.refresh()
        if not startup():
            try:setstartup(True)
            except:pass
            self.refresh()
        self.timer=QTimer(self);self.timer.timeout.connect(self.check);self.timer.start(1800)
        self.hide() if auto else self.show()
    def refresh(self):self.su.setText("✓ Tự chạy cùng Windows: BẬT" if startup() else "Tự chạy cùng Windows: TẮT")
    def showagain(self):self.show();self.raise_();self.activateWindow()
    def choose(self):
        f,_=QFileDialog.getOpenFileName(self,"Chọn video","","Video (*.mp4 *.mkv *.webm *.mov *.avi *.m4v);;All Files (*.*)")
        if f:self.src=f;self.fl.setText(f);self.prepare()
    def changed(self,_):
        if self.src and Path(self.src).exists():self.wall.stop();self.proxy="";QTimer.singleShot(80,self.prepare)
    def prepare(self):
        if not self.src or not Path(self.src).exists():return
        p=self.cb.currentText();o=cache(self.src,p)
        if o.exists() and o.stat().st_size>1048576:self.proxy=str(o);self.active=p;self.start();return
        self.pick.setEnabled(False);self.cb.setEnabled(False);self.bar.show();self.enc=Enc(self.src,o,p);self.enc.status.connect(self.status.setText);self.enc.done.connect(self.done);self.enc.fail.connect(self.fail);self.enc.start()
    def done(self,f,p):self.bar.hide();self.pick.setEnabled(True);self.cb.setEnabled(True);self.proxy=f;self.active=p;self.start()
    def fail(self,e):self.bar.hide();self.pick.setEnabled(True);self.cb.setEnabled(True);QMessageBox.warning(self,"Lỗi",e)
    def start(self):
        try:self.wall.play(self.proxy);self.status.setText(f"Đang chạy: {self.active}");self.save()
        except Exception as e:QMessageBox.warning(self,"Lỗi",str(e))
    def toggle(self):
        if self.wall.p.playbackState()==QMediaPlayer.PlayingState:self.wall.p.pause();self.status.setText("Tạm dừng")
        elif self.proxy and Path(self.proxy).exists():self.wall.p.play();self.status.setText(f"Đang chạy: {self.active}")
    def stop(self):self.wall.stop();self.status.setText("Đã dừng")
    def check(self):
        f=full()
        if self.fs.isChecked() and f and self.wall.p.playbackState()==QMediaPlayer.PlayingState and not self.ap:self.wall.p.pause();self.ap=True
        elif (not f or not self.fs.isChecked()) and self.ap:self.wall.p.play();self.ap=False
    def togsu(self):
        try:setstartup(not startup());self.refresh()
        except Exception as e:QMessageBox.warning(self,"Startup",str(e))
    def save(self):
        try:CFG.write_text(json.dumps({"src":self.src,"proxy":self.proxy,"profile":self.cb.currentText(),"active":self.active,"fs":self.fs.isChecked()},ensure_ascii=False),encoding="utf-8")
        except:pass
    def load(self):
        if not CFG.exists():return
        try:
            d=json.loads(CFG.read_text(encoding="utf-8"));p=d.get("profile",DEFAULT)
            self.cb.blockSignals(True);self.cb.setCurrentText(p if p in PROFILES else DEFAULT);self.cb.blockSignals(False)
            self.src=d.get("src","");self.proxy=d.get("proxy","");self.active=d.get("active",p);self.fs.setChecked(d.get("fs",True))
            if self.src:self.fl.setText(self.src)
            if self.proxy and Path(self.proxy).exists():QTimer.singleShot(700,self.start)
            elif self.src and Path(self.src).exists():QTimer.singleShot(700,self.prepare)
        except:pass
    def closeEvent(self,e):
        if not self.quitflag:self.save();e.ignore();self.hide()
        else:e.accept()
    def exit(self):self.quitflag=True;self.save();self.wall.stop();self.tray.hide();QApplication.quit()

app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False);w=Main("--autostart" in sys.argv);sys.exit(app.exec())
