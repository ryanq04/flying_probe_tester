import sys
import numpy as np
import serial
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt
import pyqtgraph as pg

import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)


PORT = 'COM8'
BAUDRATE = 115200
ADC_LENGTH = 2048
FFT_LENGTH = 2048
SAMPLE_RATE = 1_000_000  # 1 MSps

class SignalViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Signal Viewer with FFT")
        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()

        self.image_label = QLabel("Image will appear here")
        self.image_label.setFixedSize(384, 384)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.mousePressEvent = self.get_image_click_position
        left_layout.addWidget(self.image_label)

        self.capture_button = QPushButton("Capture Image")
        self.test_button = QPushButton("Test")
        self.uart_button = QPushButton("ADC + FFT")
        self.save_button = QPushButton("Save Image")
        self.quit_button = QPushButton("Quit")

        self.capture_button.clicked.connect(self.capture_image_only)
        self.test_button.clicked.connect(self.run_test_signal)
        self.uart_button.clicked.connect(self.handle_test_uart)
        self.save_button.clicked.connect(self.save_image)
        self.quit_button.clicked.connect(self.close)

        for btn in (self.capture_button, self.test_button, self.uart_button, self.save_button, self.quit_button):
            left_layout.addWidget(btn)

        self.time_plot = pg.PlotWidget(title="Time Domain Signal")
        self.time_curve = self.time_plot.plot(pen='c')
        self.time_plot.setLabel('left', 'Amplitude')
        self.time_plot.setLabel('bottom', 'Time', units='s')
        self.time_plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        right_layout.addWidget(self.time_plot)

        self.fft_plot = pg.PlotWidget(title="FFT Output")
        self.fft_zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('w', width=1, style=Qt.DashLine))
        self.fft_curve = None
        self.fft_plot.setLabel('left', 'Magnitude (dBV)')
        self.fft_plot.setLabel('bottom', 'Frequency', units='Hz')
        self.fft_plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.fft_plot.addItem(self.fft_zero_line)
        right_layout.addWidget(self.fft_plot)

        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        central_widget.setLayout(main_layout)

    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(1000)

    def capture_image_only(self):
        self.display_dummy_image()

    def display_dummy_image(self):
        dummy_data = np.random.randint(0, 255, (144, 174), dtype=np.uint8)
        image = QImage(dummy_data.data, dummy_data.shape[1], dummy_data.shape[0],
                       dummy_data.strides[0], QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(image)
        scaled_pixmap = pixmap.scaled(self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio)
        self.image_label.setPixmap(scaled_pixmap)
        self.latest_image = dummy_data
        self.image_shape = dummy_data.shape
        self.displayed_image_size = (scaled_pixmap.width(), scaled_pixmap.height())

    def run_test_signal(self):
        t = np.linspace(0, ADC_LENGTH / SAMPLE_RATE, ADC_LENGTH)
        signal_type = np.random.choice(['sine', 'square'])
        freq = np.random.uniform(1000, 100_000)  # 1 kHz to 100 kHz

        if signal_type == 'sine':
            signal = np.sin(2 * np.pi * freq * t)
        else:
            signal = np.sign(np.sin(2 * np.pi * freq * t))

        signal += 0.2 * np.random.randn(ADC_LENGTH)  # Add some noise
        print(f"Test signal: {signal_type} wave, Frequency: {freq:.1f} Hz, with mild noise")
        self.update_plots(signal)

    def update_plots(self, signal):
        t = np.arange(len(signal)) / SAMPLE_RATE
        signal_volts = (signal * 3.3 / 4095.0)
        self.time_curve.setData(t, signal_volts)
        fft = np.abs(np.fft.rfft(signal_volts))
        fft_db = 20 * np.log10((fft * 3.3 / 4095.0) + 1e-12)  # Avoid log(0)
        freqs = np.fft.rfftfreq(len(signal), d=1/SAMPLE_RATE)

        if self.fft_curve is None:
            self.fft_curve = pg.PlotDataItem(freqs, fft_db, pen='y')
            self.fft_plot.addItem(self.fft_curve)
        else:
            self.fft_curve.setData(freqs, fft_db)

    def get_image_click_position(self, event):
        if hasattr(self, 'image_shape') and self.image_label.pixmap() is not None:
            label_width = self.image_label.width()
            label_height = self.image_label.height()
            displayed_width, displayed_height = self.displayed_image_size

            offset_x = (label_width - displayed_width) // 2
            offset_y = (label_height - displayed_height) // 2

            x = event.pos().x() - offset_x
            y = event.pos().y() - offset_y

            if 0 <= x < displayed_width and 0 <= y < displayed_height:
                img_height, img_width = self.image_shape
                img_x = int(x * img_width / displayed_width)
                img_y = int(y * img_height / displayed_height)
                print(f"Clicked on actual image at: ({img_x}, {img_y})")
            else:
                print("Click was outside of image area.")

    def update_plot(self):
        pass

    def save_image(self):
        if hasattr(self, 'latest_image'):
            image = QImage(self.latest_image.data, self.latest_image.shape[1], self.latest_image.shape[0],
                           self.latest_image.strides[0], QImage.Format_Grayscale8)
            image.save("captured_image.png")

    def handle_test_uart(self):
        try:
            with serial.Serial(PORT, BAUDRATE, timeout=2) as ser:
                print("Waiting for ADC preamble...")
                while ser.readline().decode().strip() != "ADC":
                    pass

                adc_data = ser.read(ADC_LENGTH * 2)
                adc_values = np.frombuffer(adc_data, dtype=np.uint16)
                t = np.arange(len(adc_values)) / SAMPLE_RATE
                self.time_curve.setData(t, adc_values)

                print("Waiting for FFT preamble...")
                while ser.readline().decode().strip() != "FFT":
                    pass

                freqs = ser.read((FFT_LENGTH // 2) * 4)
                mags = ser.read((FFT_LENGTH // 2) * 4)
                frequencies = np.frombuffer(freqs, dtype='<f4')
                magnitudes = np.frombuffer(mags, dtype='<f4')

                magnitudes_db = 20 * np.log10((magnitudes * 3.3 / 4095.0) + 1e-12 )  # Convert to dBV

                print("FFT magnitudes stats (dBV):")
                print("Min:", np.min(magnitudes_db))
                print("Max:", np.max(magnitudes_db))
                print("Mean:", np.mean(magnitudes_db))
                print("Any NaNs?", np.isnan(magnitudes_db).any())
                print("First 10 FFT bins:")
                for i in range(min(10, len(frequencies))):
                    print(f"  Bin {i}: {frequencies[i]:.1f} Hz -> {magnitudes_db[i]:.2f} dBV")
                if not np.isnan(magnitudes_db).any():
                    if self.fft_curve is None:
                        self.fft_curve = pg.PlotDataItem(frequencies, magnitudes_db, pen='y')
                        self.fft_plot.addItem(self.fft_curve)
                    else:
                        self.fft_curve.setData(frequencies, magnitudes_db)
                else:
                    print("Invalid FFT data received – skipping plot.")

        except Exception as e:
            print(f"Error during UART communication: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = SignalViewer()
    viewer.show()
    sys.exit(app.exec_())
