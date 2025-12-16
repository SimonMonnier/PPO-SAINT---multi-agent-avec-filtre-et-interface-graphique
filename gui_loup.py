import sys
import io

from PySide6 import QtWidgets, QtCore, QtGui
import MetaTrader5 as mt5

from loup_live import LiveConfig, TradingAgent  # adapte le nom du fichier si besoin


# ============================================================
# Redirection des print vers la GUI
# ============================================================

class LogEmitter(QtCore.QObject):
    message = QtCore.Signal(str)


class QtLogStream(io.TextIOBase):
    def __init__(self, emitter: LogEmitter, stream_name: str):
        super().__init__()
        self.emitter = emitter
        self.stream_name = stream_name

    def write(self, msg: str):
        msg = str(msg)
        if msg.strip():  # on évite les lignes vides
            self.emitter.message.emit(f"{msg.rstrip()}")

    def flush(self):
        pass


# ============================================================
# Fenêtre principale
# ============================================================

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # --- Config & Agent ---
        self.cfg = LiveConfig(side="duel")  # LONG ONLY comme tu le souhaites
        self.agent = TradingAgent(self.cfg)

        self.setWindowTitle("Loup Ω – BTCUSD M1 Duel")
        self.setMinimumSize(700, 400)

        # ---------- Redirection stdout/stderr ----------
        self.log_emitter = LogEmitter()
        self.log_emitter.message.connect(self.on_new_log)

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = QtLogStream(self.log_emitter, "OUT")
        sys.stderr = QtLogStream(self.log_emitter, "ERR")

        # ============ UI PRINCIPALE ============
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Titre
        title = QtWidgets.QLabel("🐺 Loup Ω – BTCUSD M1")
        font = QtGui.QFont()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Agent RL en live sur MT5 – Mode Duel, sans TP fixe (SL initial + break-even + trailing)."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # --- Ligne info + lot ---
        top_layout = QtWidgets.QHBoxLayout()

        lot_label = QtWidgets.QLabel("Taille de position (lot BTC) :")
        top_layout.addWidget(lot_label)

        self.lot_spin = QtWidgets.QDoubleSpinBox()
        self.lot_spin.setDecimals(2)
        self.lot_spin.setMinimum(0.01)
        self.lot_spin.setMaximum(1.00)
        self.lot_spin.setSingleStep(0.01)
        self.lot_spin.setValue(self.cfg.position_size)
        self.lot_spin.setSuffix(" lot")
        self.lot_spin.setFixedWidth(120)
        top_layout.addWidget(self.lot_spin)

        top_layout.addStretch()

        layout.addLayout(top_layout)

        # --- Boutons Start / Stop ---
        btn_layout = QtWidgets.QHBoxLayout()

        self.start_btn = QtWidgets.QPushButton("▶️ Démarrer l’IA")
        self.start_btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 8px;")
        self.start_btn.clicked.connect(self.on_start)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QtWidgets.QPushButton("⏹️ Arrêter l’IA")
        self.stop_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 8px;")
        self.stop_btn.clicked.connect(self.on_stop)
        btn_layout.addWidget(self.stop_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # --- Statut du bot ---
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --- Equity / balance ---
        self.equity_label = QtWidgets.QLabel("Equity : N/A | Balance : N/A | Margin : N/A")
        self.equity_label.setWordWrap(True)
        layout.addWidget(self.equity_label)

        # --- Zone de log ---
        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Logs de l’IA, de MT5 et du système…")
        layout.addWidget(self.log_box, stretch=1)

        # Timer pour rafraîchir le statut du bot
        self.status_timer = QtCore.QTimer(self)
        self.status_timer.setInterval(1000)  # 1 sec
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start()

        # Timer pour rafraîchir equity / balance
        self.equity_timer = QtCore.QTimer(self)
        self.equity_timer.setInterval(5000)  # 5 sec
        self.equity_timer.timeout.connect(self.update_equity)
        self.equity_timer.start()

        self.update_status()
        self.update_equity()

    # ====================================================
    # Gestion des boutons
    # ====================================================

    def on_start(self):
        new_lot = float(self.lot_spin.value())
        self.cfg.position_size = new_lot
        self.log(f"[GUI] Démarrage du bot avec lot={new_lot:.2f}")
        self.agent.start()
        self.update_status()

    def on_stop(self):
        self.log("[GUI] Arrêt du bot demandé.")
        self.agent.stop()
        self.update_status()

    # ====================================================
    # Log & statut
    # ====================================================

    def on_new_log(self, text: str):
        # Appelé pour chaque print (y compris depuis le thread du bot)
        self.log_box.appendPlainText(text)

    def log(self, msg: str):
        self.log_box.appendPlainText(msg)

    def update_status(self):
        running = self.agent._running
        lot = self.cfg.position_size
        if running:
            text = f"État bot : ✅ EN COURS | lot={lot:.2f}"
        else:
            text = f"État bot : ⏹️ ARRÊTÉ | lot={lot:.2f}"
        self.status_label.setText(text)

    def update_equity(self):
        try:
            # On initialise MT5 si besoin (idempotent)
            mt5.initialize()
            info = mt5.account_info()
            if info is None:
                self.equity_label.setText("Equity : N/A | Balance : N/A | Margin : N/A (MT5 non connecté)")
                return

            equity = float(info.equity)
            balance = float(info.balance)
            margin = float(info.margin)

            self.equity_label.setText(
                f"Equity : {equity:.2f} | Balance : {balance:.2f} | Margin : {margin:.2f}"
            )
        except Exception as e:
            self.equity_label.setText(f"Equity : erreur ({e})")

    # ====================================================
    # Fermeture propre
    # ====================================================

    def closeEvent(self, event: QtGui.QCloseEvent):
        # on restaure stdout/stderr
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr

        if self.agent._running:
            self.log("[GUI] Fermeture de la fenêtre → arrêt du bot…")
            self.agent.stop()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
