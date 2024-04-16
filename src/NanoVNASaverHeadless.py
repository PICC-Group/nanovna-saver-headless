from .Hardware import Hardware as hw
from .Calibration import Calibration
from .CalibrationGuide import CalibrationGuide
from .Touchstone import Touchstone
from .SweepWorker import SweepWorker
from datetime import datetime
import threading
import matplotlib.pyplot as plt
import numpy as np
import csv


class NanoVNASaverHeadless:
    def __init__(self, vna_index=0, verbose=False, save_path="./Save.s2p"):
        """Initialize a NanoVNASaverHeadless object.

        Args:
            vna_index (int): Number of NanoVNAs to connect, at the moment multiple VNAs are not supported. Defaults to 0.
            verbose (bool): Print information. Defaults to False.
            save_path (str): The path to save data to. Defaults to "./Save.s2p".
        """
        self.verbose = verbose
        self.save_path = save_path
        self.iface = hw.get_interfaces()[vna_index]
        self.vna = hw.get_VNA(self.iface)
        self.calibration = Calibration()
        self.touchstone = Touchstone(self.save_path)  # s2p for two port nanovnas.
        self.worker = SweepWorker(self.vna, self.calibration, self.touchstone, verbose)
        self.CalibrationGuide = CalibrationGuide(self.calibration, self.worker, verbose)
        if self.verbose:
            print("VNA is connected: ", self.vna.connected())
            print("Firmware: ", self.vna.readFirmware())
            print("Features: ", self.vna.read_features())

    def calibrate(self, savefile=None, load_file=False):
        """Run the calibration guide and calibrate the NanoVNA.

        Args:
            savefile (path): Path to save the calibration. Defaults to None.
            load_file (bool, optional): Path to existing calibration. Defaults to False.
        """
        if load_file:
            self.CalibrationGuide.loadCalibration(load_file)
            return
        proceed = self.CalibrationGuide.automaticCalibration()
        while proceed:
            proceed = self.CalibrationGuide.automaticCalibrationStep()
        if savefile is None:
            savefile = f"./Calibration_file_{datetime.now()}.s2p"
        self.CalibrationGuide.saveCalibration(savefile)

    def set_sweep(self, start, stop, segments, points):
        """Set the sweep parameters.

        Args:
            start (int): The start frequnecy.
            stop (int): The stop frequency.
            segments (int): Number of segments.
            points (int): Number of points.
        """
        self.worker.sweep.update(start, stop, segments, points)
        if self.verbose:
            print(
                "Sweep set from "
                + str(self.worker.sweep.start / 1e9)
                + "e9"
                + " to "
                + str(self.worker.sweep.end / 1e9)
                + "e9"
            )

    def single_sweep(self):
        self.worker.sweep.set_mode("SINGLE")
        self.worker.run()
        return self._get_data()

    def stream_data(self):
        """Creates a data stream from the continuous sweeping.

        Yields:
            list: Yields a list of data when new data is available.
        """
        self._stream_data()
        try:
            for data in self._access_data():
                yield data  # Yield each piece of data as it comes
        except Exception as e:
            if self.verbose:
                print("Exception in data stream: ", e)
        finally:
            if self.verbose:
                print("Stopping worker.")
            self._stop_worker()

    def _stream_data(self):
        """Starts a thread for the sweep workers run function."""
        self.worker.sweep.set_mode("CONTINOUS")
        # Start the worker in a new thread
        self.worker_thread = threading.Thread(target=self.worker.run)
        self.worker_thread.start()

    def _access_data(self):
        """Fetches the data from the sweep worker as long as it is running a sweep.

        Yields:
            list: List of data from the latest sweep.
        """
        # Access data while the worker is running
        while self.worker.running:
            yield self._get_data()

    def _stop_worker(self):
        """Stop the sweep worker and kill the stream."""
        if self.verbose:
            print("NanoVNASaverHeadless is stopping sweepworker now.")
        self.worker.running = False
        self.worker_thread.join()

    def _get_data(self):
        """Get data from the sweep worker.

        Returns:
            list: Real Reflection, Imaginary Reflection, Real Through, Imaginary Through, Frequency
        """
        data_s11 = self.worker.data11
        data_s21 = self.worker.data21
        refl_re = []
        refl_im = []
        thru_re = []
        thru_im = []
        freq = []
        for datapoint in data_s11:
            refl_re.append(datapoint.re)
            refl_im.append(datapoint.im)
            freq.append(datapoint.freq)
        for datapoint in data_s21:
            thru_re.append(datapoint.re)
            thru_im.append(datapoint.im)
        return refl_re, refl_im, thru_re, thru_im, freq

    def plot(self, animate):
        if animate:
            plt.ion()
            fig, ax = plt.subplots(2, 1)
            fig.tight_layout(pad=4.0)

            # Set labels for each subplot
            for ax_item in ax.flat:
                ax_item.set(xlabel="Frequency (Hz)", ylabel="dB")

            # Initialize lines for each subplot
            (line1,) = ax[0].plot([], [], label="S11")
            (line2,) = ax[1].plot([], [], label="S21")

            # Display legend for each subplot
            ax[0].legend()
            ax[1].legend()
            plt.show()

            data = self.stream_data()
            for new_data in data:
                s11 = self.magnitude(new_data[0], new_data[1])
                s21 = self.magnitude(new_data[2], new_data[3])
                x = new_data[4]
                line1.set_data(x, s11)
                line2.set_data(x, s21)

                # Update limits and redraw the plot
                for ax_item in ax.flat:
                    ax_item.relim()  # Recalculate limits
                    ax_item.autoscale_view()  # Autoscale

                fig.canvas.draw()
                fig.canvas.flush_events()
                # plt.pause(0.01)

        else:
            data = self.single_sweep()
            magnitudeS11 = self.magnitude(data[0], data[1])
            magnitudeS21 = self.magnitude(data[2], data[3])
            x = data[4]
            y1 = magnitudeS11
            y2 = magnitudeS21

            fig, ax = plt.subplots(2, 1)
            fig.tight_layout(pad=4.0)

            # plot 1
            ax[0].plot(x, y1, label="S11")
            ax[0].legend()

            # plot 2
            ax[1].plot(x, y2, label="S21")
            ax[1].legend()

            for ax in ax.flat:
                ax.set(xlabel="Frequency (Hz)", ylabel="dB")

            plt.show()

    def magnitude(self, re_list, im_list):
        mag_list = []
        for re, im in zip(re_list, im_list):
            mag_list.append(10 * np.log10(np.sqrt(re**2 + im**2)))
        return mag_list

    def save_csv(self, filename):
        try:
            if not isinstance(filename, str):
                raise TypeError("Filename must be a string")

            if not filename.endswith(".csv"):
                filename += ".csv"
            file_path = filename
            old_data = None
            # Counter because NanoVNA sends out incorrect data the first few times
            counter = 0
            print("Starting to save...")
            with open(file_path, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["ReflRe", " ReflIm", " ThruRe", " ThruIm", " Freq"])
                data_stream = self.stream_data()
                for new_data in data_stream:
                    if new_data != old_data:
                        for data in new_data:
                            # Saves 10 sweeps
                            if counter > 5 and counter < 16:
                                writer.writerow([data])
                        old_data = new_data
                        if counter == 16:
                            print("Done!")
                        counter += 1
        except Exception as e:
            print("An error occurred:", e)

    def kill(self):
        """Disconnect the NanoVNA.

        Raises:
            Exception: If the NanoVNA was not successfully disconnected.
        """
        self._stop_worker()
        self.vna.disconnect()
        if self.vna.connected():
            raise Exception("The VNA was not successfully disconnected.")
        else:
            if self.verbose:
                print("Disconnected VNA.")
            return
