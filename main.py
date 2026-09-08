import os,sys,json,ctypes,hashlib,subprocess,winreg,random
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("QT_MEDIA_BACKEND","ffmpeg")
os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES","d3d11va")

from PySide6.QtCore import Qt,QUrl,QTimer,QThread,Signal,QRect
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
            if x:
                out=x
                return False
        return True
    u.EnumWindows(cb,0)
    return out or u.FindWindowExW(0,0,"WorkerW",None)

def wrect(w):
    r=wintypes.RECT()
    if u.GetClientRect(w,ctypes.byref(r)):
        return QRect(0,0,max(1,r.right),max(1,r.bottom))
    return QRect(0,0,u.GetSystemMetrics(78),u.GetSystemMetrics(79))

def virtual_geometry():
    screens=QApplication.screens()
    if not screens:
        return QRect(0,0,u.GetSystemMetrics(78),u.GetSystemMetrics(79))
    r=QRect(screens[0].geometry())
    for s in screens[1:]:
        r=r.united(s.geometry())
    return r

def target_geometry(name):
    vg=virtual_geometry()
    if name=="Tất cả màn hình":
        return QRect(0,0,vg.width(),vg.height())
    screens=QApplication.screens()
    try:
        idx=int(name.split(" ")[2])-1
        sg=screens[idx].geometry()
        return QRect(sg.x()-vg.x(),sg.y()-vg.y(),sg.width(),sg.height())
    except:
        return QRect(0,0,vg.width(),vg.height())

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
    p=Path(src);s=p.stat();k=f"{p.resolve()}|{s.st_size}|{s.st_mtime_ns}|{prof}|library-v1"
    return CACHE/(hashlib.sha1(k.encode()).hexdigest()[:24]+".mp4")

class Enc(QThread):
    done=Signal(str,str);fail=Signal(str);status=Signal(str)
    def __init__(self,s,d,p):super().__init__();self.s=s;self.d=str(d);self.p=p
    def run(self):
        try:
            w,h,fps,crf=PROFILES[self.p]
            vf=f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=fast_bilinear,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps}"
            cmd=[imageio_ffmpeg.get_ffmpeg_exe(),"-y","-hide_banner","-loglevel","error","-i",self.s,"-map_metadata","-1","-an","-vf",vf,"-c:v","libx264","-preset","veryfast","-tune","fastdecode","-profile:v","main","-bf","0","-refs","1","-g",str(fps*2),"-crf",str(crf),"-pix_fmt","yuv420p","-movflags","+faststart",self.d]
            self.status.emit(f"Đang tối ưu {w}×{h} / {fps} FPS...")
            r=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,creationflags=0x08000000)
            if r.returncode:raise RuntimeError(r.stderr[-2500:])
            self.done.emit(self.d,self.p)
        except Exception as e:self.fail.emit(str(e))

class Wall(QWidget):
    def __init__(self):
        super().__init__()
        self.display_name="Tất cả màn hình"
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.Tool)
        self.setAttribute(Qt.WA_NativeWindow,True)
        l=QVBoxLayout(self);l.setContentsMargins(0,0,0,0)
        self.v=QVideoWidget();self.v.setAspectRatioMode(Qt.KeepAspectRatioByExpanding);l.addWidget(self.v)
        self.p=QMediaPlayer(self);self.p.setVideoOutput(self.v);self.p.setLoops(QMediaPlayer.Loops.Infinite)
    def set_display(self,name):
        self.display_name=name
        if self.isVisible():self.sync()
    def attach(self):
        self.show();h=int(self.winId());w=worker()
        if not w:return False
        u.SetParent(h,w);st=u.GetWindowLongW(h,-16);u.SetWindowLongW(h,-16,st|0x40000000|0x10000000)
        self.sync()
        QTimer.singleShot(300,self.sync)
        return True
    def sync(self):
        w=worker()
        if not w:return
        g=target_geometry(self.display_name)
        h=int(self.winId())
        u.SetWindowPos(h,0,g.x(),g.y(),g.width(),g.height(),0x0040|0x0010)
        self.resize(g.width(),g.height());self.v.setGeometry(self.rect())
    def play(self,f):
        if not self.attach():raise RuntimeError("Không gắn được wallpaper vào WorkerW")
        self.p.stop();self.p.setSource(QUrl.fromLocalFile(f));self.p.play()
    def stop(self):self.p.stop();self.hide()
    def resizeEvent(self,e):super().resizeEvent(e);self.v.setGeometry(self.rect())

class Main(QMainWindow):
    def __init__(self,auto=False):
        super().__init__()
        self.wall=Wall();self.src="";self.proxy="";self.active="";self.enc=None
        self.quitflag=False;self.ap=False;self.library=[];self.play_index=-1
        self.setWindowTitle("Video Wallpaper");self.resize(860,600)

        root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root)
        title=QLabel("VIDEO WALLPAPER");title.setStyleSheet("font-size:22px;font-weight:700");outer.addWidget(title)

        self.tabs=QTabWidget();outer.addWidget(self.tabs,1)
        self.build_library_tab()
        self.build_playlist_tab()
        self.build_display_tab()
        self.build_performance_tab()

        self.bar=QProgressBar();self.bar.setRange(0,0);self.bar.hide();outer.addWidget(self.bar)
        self.status=QLabel("Sẵn sàng");outer.addWidget(self.status)

        self.tray=QSystemTrayIcon(self);self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        m=QMenu()
        for name,fn in [("Mở",self.showagain),("Play / Pause",self.toggle),("Video tiếp theo",self.next_video),("Dừng",self.stop),("Thoát hoàn toàn",self.exit)]:
            a=QAction(name,self);a.triggered.connect(fn);m.addAction(a)
        self.tray.setContextMenu(m);self.tray.show()

        self.load();self.refresh_startup();self.refresh_displays()
        if not startup():
            try:setstartup(True)
            except:pass
            self.refresh_startup()

        self.timer=QTimer(self);self.timer.timeout.connect(self.check);self.timer.start(1800)
        self.playlist_timer=QTimer(self);self.playlist_timer.timeout.connect(self.next_video)
        self.apply_playlist_timer()
        self.hide() if auto else self.show()

    def build_library_tab(self):
        tab=QWidget();l=QVBoxLayout(tab)
        self.library_list=QListWidget();self.library_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.library_list.itemDoubleClicked.connect(lambda _:self.play_selected())
        l.addWidget(self.library_list,1)
        r=QHBoxLayout()
        self.add_btn=QPushButton("Thêm video");self.remove_btn=QPushButton("Xóa khỏi thư viện")
        self.play_btn=QPushButton("Đặt làm hình nền");self.pp=QPushButton("Play / Pause");self.st=QPushButton("Dừng")
        for b in (self.add_btn,self.remove_btn,self.play_btn,self.pp,self.st):r.addWidget(b)
        l.addLayout(r)
        self.add_btn.clicked.connect(self.add_videos);self.remove_btn.clicked.connect(self.remove_selected)
        self.play_btn.clicked.connect(self.play_selected);self.pp.clicked.connect(self.toggle);self.st.clicked.connect(self.stop)
        self.tabs.addTab(tab,"Thư viện")

    def build_playlist_tab(self):
        tab=QWidget();l=QVBoxLayout(tab)
        info=QLabel("Playlist dùng toàn bộ video trong Thư viện.");l.addWidget(info)
        self.playlist_enabled=QCheckBox("Tự động đổi hình nền");l.addWidget(self.playlist_enabled)
        r=QHBoxLayout();r.addWidget(QLabel("Đổi sau:"))
        self.interval=QSpinBox();self.interval.setRange(1,1440);self.interval.setValue(30);self.interval.setSuffix(" phút")
        r.addWidget(self.interval);r.addStretch();l.addLayout(r)
        self.random_mode=QCheckBox("Phát ngẫu nhiên");l.addWidget(self.random_mode)
        r=QHBoxLayout();self.prev_btn=QPushButton("← Trước");self.next_btn=QPushButton("Tiếp →")
        r.addWidget(self.prev_btn);r.addWidget(self.next_btn);r.addStretch();l.addLayout(r);l.addStretch()
        self.playlist_enabled.toggled.connect(self.apply_playlist_timer)
        self.interval.valueChanged.connect(self.apply_playlist_timer)
        self.prev_btn.clicked.connect(self.prev_video);self.next_btn.clicked.connect(self.next_video)
        self.tabs.addTab(tab,"Playlist")

    def build_display_tab(self):
        tab=QWidget();l=QVBoxLayout(tab)
        l.addWidget(QLabel("Chọn màn hình hiển thị wallpaper:"))
        self.display_cb=QComboBox();l.addWidget(self.display_cb)
        self.display_cb.currentTextChanged.connect(self.display_changed)
        self.display_info=QLabel();self.display_info.setWordWrap(True);l.addWidget(self.display_info)
        l.addStretch();self.tabs.addTab(tab,"Màn hình")

    def build_performance_tab(self):
        tab=QWidget();l=QVBoxLayout(tab)
        r=QHBoxLayout();r.addWidget(QLabel("Chất lượng:"))
        self.cb=QComboBox();self.cb.addItems(PROFILES);self.cb.setCurrentText(DEFAULT);r.addWidget(self.cb);l.addLayout(r)
        self.cb.currentTextChanged.connect(self.changed)
        self.fs=QCheckBox("Tạm dừng khi game/app fullscreen");self.fs.setChecked(True);l.addWidget(self.fs)
        self.su=QPushButton();self.su.clicked.connect(self.togsu);l.addWidget(self.su)
        clear=QPushButton("Xóa cache video đã tối ưu");clear.clicked.connect(self.clear_cache);l.addWidget(clear)
        l.addStretch();self.tabs.addTab(tab,"Hiệu năng")

    def refresh_displays(self):
        cur=self.display_cb.currentText() if self.display_cb.count() else "Tất cả màn hình"
        self.display_cb.blockSignals(True);self.display_cb.clear();self.display_cb.addItem("Tất cả màn hình")
        for i,s in enumerate(QApplication.screens(),1):
            g=s.geometry();self.display_cb.addItem(f"Màn hình {i} — {g.width()}×{g.height()}")
        idx=self.display_cb.findText(cur)
        self.display_cb.setCurrentIndex(idx if idx>=0 else 0)
        self.display_cb.blockSignals(False);self.display_changed(self.display_cb.currentText())

    def refresh_startup(self):self.su.setText("✓ Tự chạy cùng Windows: BẬT" if startup() else "Tự chạy cùng Windows: TẮT")
    def showagain(self):self.show();self.raise_();self.activateWindow()

    def add_videos(self):
        files,_=QFileDialog.getOpenFileNames(self,"Thêm video","","Video (*.mp4 *.mkv *.webm *.mov *.avi *.m4v);;All Files (*.*)")
        changed=False
        for f in files:
            if f and f not in self.library:
                self.library.append(f);changed=True
        if changed:self.refresh_library();self.save()

    def refresh_library(self):
        self.library=[f for f in self.library if Path(f).exists()]
        self.library_list.clear()
        for f in self.library:
            item=QListWidgetItem(Path(f).name);item.setToolTip(f);item.setData(Qt.UserRole,f);self.library_list.addItem(item)
        if self.src in self.library:
            self.library_list.setCurrentRow(self.library.index(self.src))

    def remove_selected(self):
        row=self.library_list.currentRow()
        if row<0:return
        f=self.library[row]
        self.library.pop(row)
        if f==self.src:
            self.stop();self.src="";self.proxy=""
        self.refresh_library();self.save()

    def play_selected(self):
        row=self.library_list.currentRow()
        if row<0:
            if self.library:self.library_list.setCurrentRow(0);row=0
            else:return
        self.play_index=row;self.play_source(self.library[row])

    def play_source(self,f):
        if not Path(f).exists():return
        self.src=f;self.proxy=""
        if f in self.library:self.play_index=self.library.index(f)
        self.prepare()

    def next_video(self):
        if not self.library:return
        if self.random_mode.isChecked() and len(self.library)>1:
            choices=[i for i in range(len(self.library)) if i!=self.play_index]
            self.play_index=random.choice(choices)
        else:self.play_index=(self.play_index+1)%len(self.library)
        self.library_list.setCurrentRow(self.play_index);self.play_source(self.library[self.play_index])

    def prev_video(self):
        if not self.library:return
        self.play_index=(self.play_index-1)%len(self.library)
        self.library_list.setCurrentRow(self.play_index);self.play_source(self.library[self.play_index])

    def apply_playlist_timer(self):
        if not hasattr(self,"playlist_timer"):return
        if self.playlist_enabled.isChecked():
            self.playlist_timer.start(self.interval.value()*60*1000)
        else:self.playlist_timer.stop()
        self.save()

    def display_changed(self,name):
        if not name:return
        self.wall.set_display(name)
        self.display_info.setText("Wallpaper sẽ phủ toàn bộ desktop." if name=="Tất cả màn hình" else f"Wallpaper chỉ hiển thị trên {name.split(' — ')[0]}.")
        self.save()

    def changed(self,_):
        if self.src and Path(self.src).exists():
            self.wall.stop();self.proxy="";QTimer.singleShot(80,self.prepare)
        self.save()

    def prepare(self):
        if not self.src or not Path(self.src).exists():return
        p=self.cb.currentText();o=cache(self.src,p)
        if o.exists() and o.stat().st_size>1048576:
            self.proxy=str(o);self.active=p;self.start();return
        self.add_btn.setEnabled(False);self.play_btn.setEnabled(False);self.cb.setEnabled(False);self.bar.show()
        self.enc=Enc(self.src,o,p);self.enc.status.connect(self.status.setText);self.enc.done.connect(self.done);self.enc.fail.connect(self.fail);self.enc.start()

    def done(self,f,p):
        self.bar.hide();self.add_btn.setEnabled(True);self.play_btn.setEnabled(True);self.cb.setEnabled(True)
        self.proxy=f;self.active=p;self.start()

    def fail(self,e):
        self.bar.hide();self.add_btn.setEnabled(True);self.play_btn.setEnabled(True);self.cb.setEnabled(True)
        QMessageBox.warning(self,"Lỗi",e)

    def start(self):
        try:
            self.wall.set_display(self.display_cb.currentText())
            self.wall.play(self.proxy)
            self.status.setText(f"Đang chạy: {Path(self.src).name} • {self.active}")
            self.save()
        except Exception as e:QMessageBox.warning(self,"Lỗi",str(e))

    def toggle(self):
        if self.wall.p.playbackState()==QMediaPlayer.PlayingState:
            self.wall.p.pause();self.status.setText("Tạm dừng")
        elif self.proxy and Path(self.proxy).exists():
            self.wall.p.play();self.status.setText(f"Đang chạy: {Path(self.src).name}")

    def stop(self):self.wall.stop();self.status.setText("Đã dừng")

    def check(self):
        f=full()
        if self.fs.isChecked() and f and self.wall.p.playbackState()==QMediaPlayer.PlayingState and not self.ap:
            self.wall.p.pause();self.ap=True
        elif (not f or not self.fs.isChecked()) and self.ap:
            self.wall.p.play();self.ap=False

    def togsu(self):
        try:setstartup(not startup());self.refresh_startup();self.save()
        except Exception as e:QMessageBox.warning(self,"Startup",str(e))

    def clear_cache(self):
        self.wall.stop()
        n=0
        try:
            for f in CACHE.glob("*.mp4"):
                try:f.unlink();n+=1
                except:pass
            self.proxy=""
            self.status.setText(f"Đã xóa {n} file cache")
        except Exception as e:QMessageBox.warning(self,"Cache",str(e))

    def save(self):
        if not hasattr(self,"cb"):return
        try:
            CFG.write_text(json.dumps({
                "library":self.library,
                "src":self.src,"proxy":self.proxy,
                "profile":self.cb.currentText(),"active":self.active,
                "fs":self.fs.isChecked(),
                "playlist_enabled":self.playlist_enabled.isChecked(),
                "playlist_interval":self.interval.value(),
                "playlist_random":self.random_mode.isChecked(),
                "play_index":self.play_index,
                "display":self.display_cb.currentText()
            },ensure_ascii=False),encoding="utf-8")
        except:pass

    def load(self):
        if not CFG.exists():
            self.refresh_library();return
        try:
            d=json.loads(CFG.read_text(encoding="utf-8"))
            p=d.get("profile",DEFAULT)
            self.cb.blockSignals(True);self.cb.setCurrentText(p if p in PROFILES else DEFAULT);self.cb.blockSignals(False)
            self.fs.setChecked(d.get("fs",True))
            self.library=d.get("library",[])
            oldsrc=d.get("src","")
            if oldsrc and oldsrc not in self.library and Path(oldsrc).exists():self.library.append(oldsrc)
            self.src=oldsrc;self.proxy=d.get("proxy","");self.active=d.get("active",p);self.play_index=d.get("play_index",-1)
            self.playlist_enabled.setChecked(d.get("playlist_enabled",False))
            self.interval.setValue(d.get("playlist_interval",30))
            self.random_mode.setChecked(d.get("playlist_random",False))
            self.refresh_library()
            wanted=d.get("display","Tất cả màn hình")
            QTimer.singleShot(0,lambda:self.restore_display(wanted))
            if self.proxy and Path(self.proxy).exists():QTimer.singleShot(700,self.start)
            elif self.src and Path(self.src).exists():QTimer.singleShot(700,self.prepare)
        except:pass

    def restore_display(self,wanted):
        i=self.display_cb.findText(wanted)
        if i>=0:self.display_cb.setCurrentIndex(i)

    def closeEvent(self,e):
        if not self.quitflag:self.save();e.ignore();self.hide()
        else:e.accept()

    def exit(self):
        self.quitflag=True;self.save();self.wall.stop();self.tray.hide();QApplication.quit()

app=QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
w=Main("--autostart" in sys.argv)
sys.exit(app.exec())
