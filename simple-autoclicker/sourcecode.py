import sys
import json
import time
import threading
import pyautogui
import os
from pynput import mouse, keyboard
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.0

class MiniStatus(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            background: rgba(30, 30, 30, 180);
            color: #66ff66;
            border: 1px solid #444;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 14px;
        """)
        self.setText("Ultra Clicker v2.8")
        self.adjustSize()

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 20, 10)

        self.setCursor(Qt.PointingHandCursor)
        self.mousePressEvent = lambda e: parent.toggle_mini_mode()

class AutoClicker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.clicking = False
        self.macro_running = False
        self.recording = False
        self.macro = []
        self.hotkey = None
        self.hotkey_is_mouse = False
        self.hotkey_kb_listener = None
        self.hotkey_mouse_listener = None
        self.click_thread = None
        self.macro_thread = None
        self.record_mouse = None
        self.record_kb = None
        self.record_start = None
        self.stop_event = threading.Event()
        self.tabs = None
        self.mini_status = None
        self.main_visible = True
        self.f12_listener = None

        self.setup_window()
        self.setup_tray()
        self.load_settings()

        # Global F12 listener
        from pynput.keyboard import GlobalHotKeys
        self.f12_listener = GlobalHotKeys({'<f12>': self.toggle_mini_mode})
        self.f12_listener.start()

        QTimer.singleShot(500, self.setup_hotkey_listener)

        self.showMinimized()

    def setup_window(self):
        self.setWindowTitle("Ultra Clicker v2.8")
        self.setGeometry(100, 100, 800, 600)

        self.setWindowFlags(
            self.windowFlags() |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.make_clicker_tab(self.tabs)
        self.make_macro_tab(self.tabs)

        self.status = QLabel("Ready (minimized)")
        self.statusBar().addWidget(self.status)

        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; color: #e0e0e0; }
            QTabWidget::pane { border: 1px solid #444; background: #2a2a2a; }
            QTabBar::tab { background: #333; color: #aaa; padding: 10px; }
            QTabBar::tab:selected { background: #444; color: white; }
            QGroupBox { border: 1px solid #555; margin-top: 12px; font-weight: bold; color: #ddd; }
            QPushButton { background: #3a3a3a; border: 1px solid #555; padding: 10px; border-radius: 4px; color: white; }
            QPushButton:hover { background: #505050; }
            QPushButton:pressed { background: #2a2a2a; }
            QSpinBox, QDoubleSpinBox, QComboBox { background: #2e2e2e; color: white; border: 1px solid #555; padding: 6px; }
            QLabel { color: #ccc; }
            QListWidget { background: #2a2a2a; color: white; border: 1px solid #555; }
            QListWidget::item:selected { background: #0066cc; }
        """)

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))

        menu = QMenu()
        show = QAction("Show Main", self)
        show.triggered.connect(self.show_main)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.full_quit)

        menu.addAction(show)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)
        self.tray.show()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_main()

    def show_main(self):
        if self.mini_status:
            self.mini_status.hide()
        self.showNormal()
        self.activateWindow()
        self.raise_()
        self.main_visible = True

    @pyqtSlot()
    def toggle_mini_mode(self):
        if self.main_visible:
            self.hide()
            if not self.mini_status:
                self.mini_status = MiniStatus()
            self.mini_status.show()
            self.mini_status.raise_()
            self.main_visible = False
        else:
            if self.mini_status:
                self.mini_status.hide()
            self.showNormal()
            self.activateWindow()
            self.raise_()
            self.main_visible = True

    def full_quit(self):
        self.close()
        QApplication.quit()
        sys.exit(0)

    def closeEvent(self, event):
        self.clicking = False
        self.macro_running = False
        self.recording = False
        self.stop_event.set()

        # Stop threads
        for t in [self.click_thread, self.macro_thread]:
            if t and t.is_alive():
                t.join(timeout=1.0)

        # Stop ALL listeners
        for l in [
            self.hotkey_kb_listener,
            self.hotkey_mouse_listener,
            self.record_mouse,
            self.record_kb,
            self.f12_listener
        ]:
            if l:
                try:
                    l.stop()
                except:
                    pass

        self.save_settings()

        # Clean tray
        if hasattr(self, 'tray') and self.tray:
            self.tray.hide()
            self.tray = None

        # Clean mini
        if self.mini_status:
            self.mini_status.hide()
            self.mini_status.deleteLater()
            self.mini_status = None

        event.accept()
        QApplication.quit()
        sys.exit(0)

    def make_clicker_tab(self, tabs):
        tab = QWidget()
        lay = QVBoxLayout(tab)

        g = QGroupBox("Hotkey")
        hl = QVBoxLayout()
        self.hotkey_lbl = QLabel("Hotkey: not set")
        self.hotkey_lbl.setStyleSheet("font-weight: bold; color: #66ff66;")
        hl.addWidget(self.hotkey_lbl)

        btn = QPushButton("Set Hotkey")
        btn.clicked.connect(self.set_hotkey)
        btn.setStyleSheet("background: #0066cc; font-weight: bold;")
        hl.addWidget(btn)
        g.setLayout(hl)
        lay.addWidget(g)

        g = QGroupBox("Click Settings")
        gl = QGridLayout()
        gl.addWidget(QLabel("Delay (ms):"), 0, 0)
        self.delay_box = QSpinBox()
        self.delay_box.setRange(0, 10000)
        self.delay_box.setValue(10)
        self.delay_box.setSuffix(" ms")
        gl.addWidget(self.delay_box, 0, 1)

        gl.addWidget(QLabel("Type:"), 1, 0)
        self.type_box = QComboBox()
        self.type_box.addItems(["Single", "Double"])
        gl.addWidget(self.type_box, 1, 1)

        gl.addWidget(QLabel("Button:"), 2, 0)
        self.btn_box = QComboBox()
        self.btn_box.addItems(["Left", "Right", "Middle"])
        gl.addWidget(self.btn_box, 2, 1)
        g.setLayout(gl)
        lay.addWidget(g)

        g = QGroupBox("Controls")
        cl = QHBoxLayout()
        self.startb = QPushButton("START")
        self.stopb = QPushButton("STOP")
        testb = QPushButton("Test Click")

        self.startb.clicked.connect(self.start_click)
        self.stopb.clicked.connect(self.stop_click)
        testb.clicked.connect(self.test_click)

        self.stopb.setEnabled(False)
        for b in [self.startb, self.stopb, testb]:
            b.setMinimumHeight(48)
            cl.addWidget(b)
        g.setLayout(cl)
        lay.addWidget(g)

        lay.addStretch()
        tabs.addTab(tab, "Clicker")

    def make_macro_tab(self, tabs):
        tab = QWidget()
        lay = QVBoxLayout(tab)

        g = QGroupBox("Recording")
        rl = QVBoxLayout()

        bl = QHBoxLayout()
        self.record = QPushButton("Record")
        self.stoprec = QPushButton("Stop Rec")
        self.play = QPushButton("Play")
        self.stopplay = QPushButton("Stop Play")
        self.save = QPushButton("Save")
        self.load = QPushButton("Load")

        for b in [self.record, self.stoprec, self.play, self.stopplay, self.save, self.load]:
            b.setMinimumHeight(48)
            bl.addWidget(b)

        self.record.clicked.connect(self.start_rec)
        self.stoprec.clicked.connect(self.stop_rec)
        self.play.clicked.connect(self.start_macro)
        self.stopplay.clicked.connect(self.stop_macro)
        self.save.clicked.connect(self.save_macro)
        self.load.clicked.connect(self.load_macro)

        self.stoprec.setEnabled(False)
        self.play.setEnabled(False)
        self.save.setEnabled(False)
        self.stopplay.setEnabled(False)

        rl.addLayout(bl)

        self.macro_info = QLabel("No macro loaded")
        rl.addWidget(self.macro_info)

        ll = QHBoxLayout()
        self.mlist = QListWidget()
        self.mlist.setMinimumHeight(180)
        self.mlist.setSelectionMode(QListWidget.ExtendedSelection)
        self.mlist.itemSelectionChanged.connect(self.on_macro_select)
        ll.addWidget(self.mlist)

        ab = QVBoxLayout()
        self.delsel = QPushButton("Delete Selected")
        self.clearall = QPushButton("Clear All")
        self.delsel.clicked.connect(self.delete_selected)
        self.clearall.clicked.connect(self.clear_macro)
        self.delsel.setEnabled(False)
        self.clearall.setEnabled(False)
        ab.addWidget(self.delsel)
        ab.addWidget(self.clearall)
        ab.addStretch()
        ll.addLayout(ab)

        rl.addWidget(QLabel("Actions:"))
        rl.addLayout(ll)

        g.setLayout(rl)
        lay.addWidget(g)

        g = QGroupBox("Playback")
        pl = QGridLayout()
        pl.addWidget(QLabel("Repeats:"), 0, 0)
        self.repeat_box = QSpinBox()
        self.repeat_box.setRange(1, 9999)
        self.repeat_box.setValue(1)
        pl.addWidget(self.repeat_box, 0, 1)

        pl.addWidget(QLabel("Speed:"), 1, 0)
        self.speed_box = QDoubleSpinBox()
        self.speed_box.setRange(0.0, 10.0)
        self.speed_box.setSingleStep(0.05)
        self.speed_box.setValue(1.0)
        self.speed_box.setSuffix(" ×")
        pl.addWidget(self.speed_box, 1, 1)

        self.hold_box = QCheckBox("Repeat while holding hotkey")
        pl.addWidget(self.hold_box, 2, 0, 1, 2)

        g.setLayout(pl)
        lay.addWidget(g)

        lay.addStretch()
        tabs.addTab(tab, "Macro")

    def on_macro_select(self):
        self.delsel.setEnabled(len(self.mlist.selectedItems()) > 0)

    def delete_selected(self):
        items = self.mlist.selectedItems()
        if not items:
            return

        idxs = sorted([self.mlist.row(i) for i in items], reverse=True)

        for i in idxs:
            if 0 <= i < len(self.macro):
                del self.macro[i]
            self.mlist.takeItem(i)

        has = len(self.macro) > 0
        self.play.setEnabled(has)
        self.save.setEnabled(has)
        self.clearall.setEnabled(has)
        self.mlist.clearSelection()
        self.delsel.setEnabled(False)
        self.status.setText(f"Deleted {len(idxs)} action(s)")

    def clear_macro(self):
        self.macro = []
        self.mlist.clear()
        self.play.setEnabled(False)
        self.save.setEnabled(False)
        self.clearall.setEnabled(False)
        self.status.setText("Macro cleared")

    def set_hotkey(self):
        self.status.setText("Press key or mouse button (Esc cancels)")

        box = QMessageBox(self)
        box.setWindowTitle("Set Hotkey")
        box.setText("Press any key or mouse button")
        box.setStandardButtons(QMessageBox.Cancel)
        box.show()

        captured = []

        def on_press(k):
            captured.append(k)
            QMetaObject.invokeMethod(box, "accept", Qt.QueuedConnection)
            return False

        def on_click(x, y, b, p):
            if p:
                captured.append(b)
                QMetaObject.invokeMethod(box, "accept", Qt.QueuedConnection)
                return False

        kb = keyboard.Listener(on_press=on_press)
        ms = mouse.Listener(on_click=on_click)
        kb.start()
        ms.start()

        res = box.exec_()

        kb.stop()
        ms.stop()

        if captured and res == QMessageBox.Accepted:
            self.hotkey = captured[0]
            self.hotkey_is_mouse = isinstance(self.hotkey, mouse.Button)

            if self.hotkey_is_mouse:
                txt = f"{str(self.hotkey).split('.')[-1].capitalize()} Mouse"
            else:
                txt = str(self.hotkey).split('.')[-1].replace('_', ' ').title()

            self.hotkey_lbl.setText(f"Hotkey: {txt}")
            self.setup_hotkey_listener()
            self.status.setText(f"Hotkey set: {txt}")
        else:
            self.status.setText("Cancelled")

    def setup_hotkey_listener(self):
        if self.hotkey_kb_listener:
            try: self.hotkey_kb_listener.stop()
            except: pass
        if self.hotkey_mouse_listener:
            try: self.hotkey_mouse_listener.stop()
            except: pass

        if not self.hotkey:
            return

        if self.hotkey_is_mouse:
            def on_click(x, y, button, pressed):
                if button == self.hotkey:
                    if pressed:
                        QMetaObject.invokeMethod(self, "hotkey_down", Qt.QueuedConnection)
                    else:
                        QMetaObject.invokeMethod(self, "hotkey_up", Qt.QueuedConnection)

            self.hotkey_mouse_listener = mouse.Listener(on_click=on_click)
            self.hotkey_mouse_listener.start()
        else:
            def on_press(key):
                if key == self.hotkey:
                    QMetaObject.invokeMethod(self, "hotkey_down", Qt.QueuedConnection)

            def on_release(key):
                if key == self.hotkey:
                    QMetaObject.invokeMethod(self, "hotkey_up", Qt.QueuedConnection)

            self.hotkey_kb_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self.hotkey_kb_listener.start()

    @pyqtSlot()
    def hotkey_down(self):
        if self.tabs is None:
            return
        try:
            tab = self.tabs.currentIndex()
            if tab == 0:
                if self.clicking:
                    self.stop_click()
                else:
                    self.start_click()
            elif tab == 1:
                if self.hold_box.isChecked():
                    if not self.macro_running:
                        self.macro_running = True
                        self.play.setEnabled(False)
                        self.stopplay.setEnabled(True)
                        self.status.setText("Macro active (hold)")
                        self.macro_thread = threading.Thread(target=self.macro_hold_loop, daemon=True)
                        self.macro_thread.start()
                else:
                    if self.macro_running:
                        self.stop_macro()
                    else:
                        self.start_macro()
        except Exception as e:
            print(f"hotkey_down error: {e}")

    @pyqtSlot()
    def hotkey_up(self):
        if self.tabs is None:
            return
        try:
            if self.tabs.currentIndex() == 1 and self.hold_box.isChecked() and self.macro_running:
                self.macro_running = False
                self.macro_done()
        except Exception as e:
            print(f"hotkey_up error: {e}")

    def start_click(self):
        if self.clicking:
            return
        self.clicking = True
        self.stop_event.clear()
        self.startb.setEnabled(False)
        self.stopb.setEnabled(True)
        self.status.setText("Clicking...")
        self.click_thread = threading.Thread(target=self.click_loop, daemon=True)
        self.click_thread.start()

    def click_loop(self):
        bmap = {"Left": "left", "Right": "right", "Middle": "middle"}
        btn = bmap[self.btn_box.currentText()]
        delay = self.delay_box.value() / 1000.0
        double = self.type_box.currentText() == "Double"

        while self.clicking and not self.stop_event.is_set():
            try:
                if double:
                    pyautogui.click(button=btn)
                    pyautogui.click(button=btn)
                else:
                    pyautogui.click(button=btn)

                time.sleep(max(delay, 0.001))
            except Exception as e:
                print(f"Click loop error: {e}")
                break

    def stop_click(self):
        self.clicking = False
        self.stop_event.set()
        self.startb.setEnabled(True)
        self.stopb.setEnabled(False)
        self.status.setText("Ready")

    def test_click(self):
        bmap = {"Left": "left", "Right": "right", "Middle": "middle"}
        btn = bmap[self.btn_box.currentText()]
        double = self.type_box.currentText() == "Double"

        try:
            if double:
                pyautogui.click(button=btn)
                pyautogui.click(button=btn)
            else:
                pyautogui.click(button=btn)
        except Exception as e:
            print(f"Test click error: {e}")

    def start_rec(self):
        self.recording = True
        self.macro = []
        self.record_start = time.time()

        self.record.setEnabled(False)
        self.stoprec.setEnabled(True)
        self.mlist.clear()

        self.status.setText("Recording…")
        self.macro_info.setText("Do your thing")

        self.start_listeners()

    def start_listeners(self):
        self.stop_event_rec = threading.Event()

        def clk(x, y, b, p):
            if self.recording and not self.stop_event_rec.is_set():
                t = time.time() - self.record_start
                a = {'type': 'click', 'x': x, 'y': y, 'button': str(b), 'pressed': p, 'time': t}
                self.macro.append(a)
                QMetaObject.invokeMethod(self, "add_action", Q_ARG(str, f"[{t:.2f}s] {'↓' if p else '↑'} {str(b).split('.')[-1]}"))

        def kp(k):
            if self.recording and not self.stop_event_rec.is_set():
                t = time.time() - self.record_start
                ks = k.char if hasattr(k, 'char') and k.char else str(k)[4:]
                a = {'type': 'key', 'key': ks, 'pressed': True, 'time': t}
                self.macro.append(a)
                QMetaObject.invokeMethod(self, "add_action", Q_ARG(str, f"[{t:.2f}s] ↓ {ks}"))

        def kr(k):
            if self.recording and not self.stop_event_rec.is_set():
                t = time.time() - self.record_start
                ks = k.char if hasattr(k, 'char') and k.char else str(k)[4:]
                a = {'type': 'key', 'key': ks, 'pressed': False, 'time': t}
                self.macro.append(a)
                QMetaObject.invokeMethod(self, "add_action", Q_ARG(str, f"[{t:.2f}s] ↑ {ks}"))

        self.record_mouse = mouse.Listener(on_click=clk)
        self.record_kb = keyboard.Listener(on_press=kp, on_release=kr)
        self.record_mouse.start()
        self.record_kb.start()

    @pyqtSlot(str)
    def add_action(self, txt):
        self.mlist.addItem(txt)

    def stop_rec(self):
        self.recording = False
        if hasattr(self, 'stop_event_rec'):
            self.stop_event_rec.set()
        self.stop_input_listeners()

        self.record.setEnabled(True)
        self.stoprec.setEnabled(False)
        has = len(self.macro) > 0
        self.play.setEnabled(has)
        self.save.setEnabled(has)
        self.clearall.setEnabled(has)

        self.status.setText("Stopped recording")
        self.macro_info.setText(f"{len(self.macro)} actions")

    def stop_input_listeners(self):
        for lst in [self.record_mouse, self.record_kb]:
            if lst:
                try: lst.stop()
                except: pass
        self.record_mouse = None
        self.record_kb = None

    def delete_selected(self):
        items = self.mlist.selectedItems()
        if not items:
            return

        idxs = sorted([self.mlist.row(i) for i in items], reverse=True)

        for i in idxs:
            if 0 <= i < len(self.macro):
                del self.macro[i]
            self.mlist.takeItem(i)

        has = len(self.macro) > 0
        self.play.setEnabled(has)
        self.save.setEnabled(has)
        self.clearall.setEnabled(has)
        self.mlist.clearSelection()
        self.delsel.setEnabled(False)
        self.status.setText(f"Deleted {len(idxs)} action(s)")

    def clear_macro(self):
        self.macro = []
        self.mlist.clear()
        self.play.setEnabled(False)
        self.save.setEnabled(False)
        self.clearall.setEnabled(False)
        self.status.setText("Macro cleared")

    def start_macro(self):
        if not self.macro or self.macro_running:
            return
        self.macro_running = True
        self.play.setEnabled(False)
        self.stopplay.setEnabled(True)
        self.status.setText("Playing…")
        self.macro_thread = threading.Thread(target=self.macro_normal, daemon=True)
        self.macro_thread.start()

    def macro_normal(self):
        reps = self.repeat_box.value()
        mult = self.speed_box.value()

        for _ in range(reps):
            if not self.macro_running:
                break
            last = 0
            for act in self.macro:
                if not self.macro_running:
                    break
                d = (act['time'] - last) * mult
                if d > 0:
                    time.sleep(d)
                last = act['time']
                self.do_action(act)
        QMetaObject.invokeMethod(self, "macro_done", Qt.QueuedConnection)

    def macro_hold_loop(self):
        mult = self.speed_box.value()
        while self.macro_running:
            last = 0
            for act in self.macro:
                if not self.macro_running:
                    break
                d = (act['time'] - last) * mult
                if d > 0:
                    time.sleep(d)
                last = act['time']
                self.do_action(act)
        QMetaObject.invokeMethod(self, "macro_done", Qt.QueuedConnection)

    def do_action(self, act):
        try:
            if act['type'] == 'click':
                pyautogui.moveTo(act['x'], act['y'], duration=0)
                b = 'left'
                if 'right' in act['button'].lower(): b = 'right'
                elif 'middle' in act['button'].lower(): b = 'middle'
                if act['pressed']:
                    pyautogui.mouseDown(button=b)
                else:
                    pyautogui.mouseUp(button=b)
            elif act['type'] == 'key':
                if act['pressed']:
                    pyautogui.keyDown(act['key'])
                else:
                    pyautogui.keyUp(act['key'])
        except Exception as e:
            print(f"Action error: {e}")

    @pyqtSlot()
    def macro_done(self):
        self.macro_running = False
        self.play.setEnabled(True)
        self.stopplay.setEnabled(False)
        self.status.setText("Ready")

    def stop_macro(self):
        self.macro_running = False
        self.macro_done()

    def save_macro(self):
        if not self.macro:
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save Macro", "", "JSON (*.json)")
        if fn:
            try:
                with open(fn, 'w') as f:
                    json.dump(self.macro, f, indent=2)
                self.status.setText("Saved")
            except:
                self.status.setText("Save failed")

    def load_macro(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Load Macro", "", "JSON (*.json)")
        if fn:
            try:
                with open(fn, 'r') as f:
                    self.macro = json.load(f)
                self.refresh_list()
                has = len(self.macro) > 0
                self.play.setEnabled(has)
                self.save.setEnabled(has)
                self.clearall.setEnabled(has)
                self.status.setText("Loaded")
            except:
                self.status.setText("Load failed")

    def refresh_list(self):
        self.mlist.clear()
        for a in self.macro:
            t = a['time']
            if a['type'] == 'click':
                b = a['button'].split('.')[-1]
                s = "↓" if a['pressed'] else "↑"
                txt = f"[{t:.2f}s] {s} {b}"
            else:
                s = "↓" if a['pressed'] else "↑"
                txt = f"[{t:.2f}s] {s} {a['key']}"
            self.mlist.addItem(txt)

    def get_config_path(self):
        return os.path.join(os.environ['TEMP'], 'ultraclicker_settings.json')

    def save_settings(self):
        s = {
            'delay': self.delay_box.value(),
            'type': self.type_box.currentIndex(),
            'button': self.btn_box.currentIndex(),
            'speed': self.speed_box.value(),
        }
        try:
            with open(self.get_config_path(), 'w') as f:
                json.dump(s, f)
        except:
            pass

    def load_settings(self):
        try:
            with open(self.get_config_path(), 'r') as f:
                s = json.load(f)
            self.delay_box.setValue(s.get('delay', 10))
            self.type_box.setCurrentIndex(s.get('type', 0))
            self.btn_box.setCurrentIndex(s.get('button', 0))
            self.speed_box.setValue(s.get('speed', 1.0))
        except:
            pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = AutoClicker()
    sys.exit(app.exec_())
