from .Hardware import Hardware as hw
from .Calibration import Calibration
from .CalibrationGuide import CalibrationGuide
from .Touchstone import Touchstone
from .RFTools import Datapoint
from .SweepWorker import SweepWorker
import matplotlib.pyplot as plt
import math


class NanoVNASaverHeadless:
    def __init__(self, vna_index=0, verbose=False):
        self.verbose = verbose
        self.iface = hw.get_interfaces()[vna_index]
        self.vna = hw.get_VNA(self.iface)
        self.calibration = Calibration()
        self.touchstone = Touchstone("Save.s2p")  # s2p for two port nanovnas.
        self.worker = SweepWorker(self.vna, self.calibration, self.touchstone, verbose)
        self.CalibrationGuide = CalibrationGuide(self.calibration, self.worker)
        if self.verbose:
            print("VNA is connected: ", self.vna.connected())
            print("Firmware: ", self.vna.readFirmware())
            print("Features: ", self.vna.read_features())

    def calibrate(self):
        proceed = self.CalibrationGuide.automaticCalibration()
        while proceed:
            proceed = self.CalibrationGuide.automaticCalibrationStep()

    def set_sweep(self, start, stop):
        self.vna.setSweep(start, stop)
        print(
            "Sweep set from "
            + str(self.vna.readFrequencies()[0] / 1e9)
            + "e9"
            + " to "
            + str(self.vna.readFrequencies()[-1] / 1e9)
            + "e9"
        )

    def stream_data(self):
        data = self.get_data()
        magnList = []
        for re, im in zip(data[0], data[1]):
            magn = math.sqrt(re**2 + im**2)
            magnList.append(magn)
        plt.plot(data[4], magnList)
        plt.show()

    def get_data(self):
        dataS11 = self.vna.readValues("data 0")
        dataS21 = self.vna.readValues("data 1")
        reflRe, reflImag = self.split_data(dataS11)
        thruRe, thruImag = self.split_data(dataS21)
        freq = self.vna.readFrequencies()
        return reflRe, reflImag, thruRe, thruImag, freq

    def make_datapoint_list(self, freqList, reList, imList):
        list = []
        for freq, re, im in zip(freqList, reList, imList):
            list.append(Datapoint(freq, re, im))
        return list

    def wait_for_ans(self, string):
        while True:
            answer = input("Connect " + string + ": ").lower()
            if answer == "done":
                print("Proceeding...")
                break
            else:
                print("Invalid input. Please enter 'done' to continue.")

    def split_data(self, data):
        real = []
        imaginary = []
        for item in data:
            values = item.split()
            real.append(float(values[0]))
            imaginary.append(float(values[1]))
        # add exception handling
        return real, imaginary

    def kill(self):
        self.vna.disconnect()
        if self.vna.connected():
            raise Exception("The VNA was not successfully disconnected.")
        else:
            if self.verbose:
                print("Disconnected VNA.")
            return
