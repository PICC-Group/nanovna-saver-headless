from src.NanoVNASaverHeadless import NanoVNASaverHeadless


############### TODO: Implement high level script for newbies. #######################

CALIBRATION_FILE = (
    "Calibration_file_2024-04-12 12:23:02.604314.s2p"
)

vna = NanoVNASaverHeadless(vna_index=0, verbose=True)
vna.calibrate(None, CALIBRATION_FILE)
vna.set_sweep(2.9e9, 3.1e9, 1, 101)

vna.plot(True)


vna.kill()
