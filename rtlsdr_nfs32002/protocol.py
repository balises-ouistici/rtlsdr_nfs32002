# License : AGPLv3

from rtlsdr import RtlSdr
import numpy as np
import scipy as sp
import asyncio

from .utils import find_runs

class RtlSdr_NFS32002:

    def __init__(self):
        self.sdr = RtlSdr()
        self.sdr.sample_rate = 1e6
        self.sdr.center_freq = 868.3e6
        self.sdr.set_manual_gain_enabled(False)
        self.filter_method = "uniform"
        self._filter = self._filter_uniform
    
    def setManualGain(self, gain):
        self.sdr.set_manual_gain_enabled(True)
        self.sdr.gain(gain)

    def setAutomaticGain(self):
        self.sdr.set_manual_gain_enabled(False)

    def setFilterMethod(self, filter_method):
        if filter_method in ["savgol","uniform"]:
            self.filter_method = filter_method
            self._filter = getattr(self, f"_filter_{filter_method}")
        else:
            raise ValueError(f"Invalid filter name: {filter_method}")

    def _filter_savgol(self, data):
        threshold = np.mean(data)/4
        normalized = np.where(data > threshold, 1, 0)
        bin_data = normalized[np.where(normalized != 0)[0][0]:]
        filtered_data = sp.signal.savgol_filter(bin_data, 50, 1)
        filtered_data = np.where(filtered_data > 0.5, 1, 0)
        filtered_data = np.append([0], filtered_data)
        return filtered_data

    def _filter_uniform(self, data):
        filtered_data = sp.ndimage.uniform_filter1d(data, size=50)
        filtered_data = np.where(filtered_data > np.amax(filtered_data)/4, 1, 0)
        filtered_data = np.append([0], filtered_data)
        return filtered_data
    
    def __detectNFS32002Frame(self, samples_array, error_rate):
        nfs32002_timings = [625, 312.5, 312.5, 207.5, 207.5, 500, 500, 250, 250, 250, 250, 500, 500, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 500, 250, 250, 500, 250, 250, 500, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250]
        
        data = np.abs(samples_array)**2
        filtered_data = self.__filter(data)
        values, timings = find_runs(filtered_data)
        error_rate_min, error_rate_max = 1-error_rate, 1+error_rate

        detected_frame = False

        i = 0
        while i < len(values):
            # Check the presence of a syncword
            data = True
            if values[i] == 1:
                j = i
                for timing in nfs32002_timings:
                    if (timings[j] >= (timing*error_rate_min) and \
                        timings[j] <= (timing*error_rate_max) and \
                        j < len(values)):
                        j += 1
                    else:
                        data = False
                        break
                if data:
                    detected_frame = True
                    break
            i += 1

        return(detected_frame)
    
    def __detectNFS32002FrameSimple(self, samples_array, error_rate):
        sequence = "001101010011010101010100101101001010101010101010"
        
        data = np.abs(samples_array)**2
        threshold = np.mean(data)/4
        normalized = np.where(data > threshold, 1, 0)
        normalized = normalized[np.where(normalized != 0)[0][0]:] # remove first zeros
        normalized = np.append([0], normalized)
        
        bin_data = normalized[0::250]
        binlist = "".join(list(map(str, bin_data.tolist())))
        
        return (sequence in binlist)

    async def __detectionLoop(self, callback, error_rate, simple_detect):
        samples_array = np.array([])
        stream = self.sdr.stream()
        
        if simple_detect:
            detect = self.__detectNFS32002FrameSimple
        else:
            detect = self.__detectNFS32002Frame
            
        async for samples in stream:
            samples_array = np.append(samples_array, samples)
       
            if len(samples_array) > 250*200:
                
                try:
                    detected = detect(samples_array, error_rate)
                except:
                    detected = False
                # Flush samples array
                samples_array = np.array([])

                if detected:
                    callback()
                    while not stream.queue.empty():
                        stream.queue.get_nowait()
                        stream.queue.task_done()


    def startDetection(self, callback, error_rate = 0.2, simple_detect = False):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.__detectionLoop(callback, error_rate, simple_detect))
