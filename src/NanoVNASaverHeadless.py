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
        self.playback_mode = False
        try:
            self.iface = hw.get_interfaces()[vna_index]
        except IndexError:
            print("NanoVNA not found, is it connected? Entering playback mode.")
            self.playback_mode = True
        if not self.playback_mode:
            self.vna = hw.get_VNA(self.iface)
            self.calibration = Calibration()
            self.touchstone = Touchstone(self.save_path)  # s2p for two port nanovnas.
            self.worker = SweepWorker(
                self.vna, self.calibration, self.touchstone, verbose
            )
            self.CalibrationGuide = CalibrationGuide(
                self.calibration, self.worker, verbose
            )
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
        if self.playback_mode:
            print("Cannot calibrate in playback mode. Connect NanoVNA and restart.")
            return
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
        if self.playback_mode:
            print("Cannot set sweep in playback mode. Connect NanoVNA and restart.")
            return
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
        if self.playback_mode:
            print("Cannot do a sweep in playback mode. Connect NanoVNA and restart.")
            return
        self.worker.sweep.set_mode("SINGLE")
        self.worker.run()
        return self._get_data()

    def stream_data(self, data_file=False):
        """Creates a data stream from the continuous sweeping. (Or a previously recorded file.)

        Args:
            data_file (string): Path to a previously recorded csv file to stream from. Defaults to False.

        Yields:
            list: Yields a list of data when new data is available.
        """
        if not data_file:
            self._stream_data()
        try:
            if not data_file:
                stream = self._access_data()
            else:
                stream = self._csv_streamer(data_file)

            for data in stream:
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

    def _csv_streamer(self, filename, data_points=5):
        """Stream previously recorded data from a csv file.

        Args:
            filename (string): Path to the csv file.
            data_points (int): Number of lines that each sweep is stored as. Defaults to 5.

        Yields:
            list: [refl_re, refl_im, thru_re, thru_im, freq]
        """
        try:
            with open(filename) as f:
                data = f.readlines()
                package = []
                counter = 0
                for i, line in enumerate(data):
                    if i != 0:
                        package.append(
                            [float(x) for x in line.replace("\n", "").split(", ")]
                        )
                        counter += 1
                        if counter == data_points:
                            yield package
                            counter = 0
                            package = []
        except Exception as e:
            print(e)

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
        if not self.playback_mode:
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

    def plot(self, animate, data_file=False, loop=False):
        """Show a magnitude plot from the data. If animate is True it will update the plot continuously with data from live stream or previously recorded file.

        Args:
            animate (bool): If the stream should be from a single sweep or continuous stream.
            data_file (bool, str): Pass a filepath to show previously recorded stream. Defaults to False.
            loop (bool): Loop the stream from the datafile. Defaults to False.
        """
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
            run = True
            while run:
                data = self.stream_data(data_file)
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
                    plt.pause(0.01)
                run = data_file and loop
                if self.verbose:
                    print("Looped the animation.")

        else:
            if self.playback_mode:
                print(
                    "Cannot run sweeps in playback mode. Connect NanoVNA and restart."
                )
                return
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
        """Function to get the magnitude and prepare for plotting.

        Args:
            re_list (list): List with real parts.
            im_list (list): List with imaginary parts.

        Returns:
            list: List with the magnitude.
        """
        mag_list = []
        for re, im in zip(re_list, im_list):
            mag_list.append(10 * np.log10(np.sqrt(re**2 + im**2)))
        return mag_list

    def save_csv(self, filename, nr_sweeps=10, skip_start=5):
        """Function to save the stream to a csv file.

        Args:
            filename (str): The filename to save to.
            nr_sweeps (int): Number of sweeps to run. Defaults to 10.
            skip_start (int): The NanoVNA usually gives bad data in the beginning, therefore this data can be skipped. Defaults to 5.

        Raises:
            TypeError: If the filename is not a string.
        """
        if self.playback_mode:
            print("Cannot run sweeps in playback mode. Connect NanoVNA and restart.")
            return
        try:
            if not isinstance(filename, str):
                raise TypeError("Filename must be a string")

            if not filename.endswith(".csv"):
                filename += ".csv"
            file_path = filename
            old_data = None
            # Counter because NanoVNA sends out incorrect data the first few times
            counter = 0
            if self.verbose:
                print("Starting to save...")
            with open(file_path, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow("ReflRe", " ReflIm", " ThruRe", " ThruIm", " Freq")
                data_stream = self.stream_data()
                for new_data in data_stream:
                    if new_data != old_data:
                        for data in new_data:
                            if (
                                counter > skip_start
                                and counter < skip_start + nr_sweeps
                            ):
                                writer.writerow(data)
                        old_data = new_data
                        counter += 1
                if self.verbose:
                    print("Done!")
        except Exception as e:
            print("An error occurred:", e)

    def kill(self):
        """Disconnect the NanoVNA.

        Raises:
            Exception: If the NanoVNA was not successfully disconnected.
        """
        if self.playback_mode:
            print("Cannot kill in playback mode. Connect NanoVNA and restart.")
            return
        self._stop_worker()
        self.vna.disconnect()
        if self.vna.connected():
            raise Exception("The VNA was not successfully disconnected.")
        else:
            if self.verbose:
                print("Disconnected VNA.")
            return
