
import time
import cv2
import numpy as np

from libcamera import controls
from picamera2 import Picamera2, Controls

from numba import jit


def getMaxAduValue(array):
    return np.max(array) #np.median(np.sort(array)[:20])


###

class IMX477Camera_CSI():
    def __init__(self):
        self._picam2 = None
        self._cameraControls = None
        self._name = "IMX477"
        self._bin = False
        self._crop_height = 220
        self._max_adu = (0,0,0)
        self._monobin_mode = 0

    def init(self):
        # load the default tuning file
        tuning = Picamera2.load_tuning_file("imx477_scientific.json")
        #tuning = Picamera2.load_tuning_file("imx477.json")
        contrast_algo = Picamera2.find_tuning_algo(tuning, "rpi.contrast")
        gamma_curve = contrast_algo["gamma_curve"]
        contrast_algo["ce_enable"] = 0
        contrast_algo["gamma_curve"] = [0, 0, 65535, 65535]
        self._picam2 = Picamera2(tuning=tuning)

        
        mode = self._picam2.sensor_modes[3]
  
        self._sensor_mode = 3
        self._sensor_size = (mode['size'][0],mode['size'][1])
        video_config = self._picam2.create_video_configuration(buffer_count=10,sensor={'output_size': mode['size'], 'bit_depth':mode['bit_depth']}, raw={"format":"SRGGB12", 'size': mode['size']})
        self._picam2.configure(video_config)
        self._picam2.set_controls({'HdrMode': controls.HdrModeEnum.Off})
        self._picam2.start()
        time.sleep(2)

        return self._sensor_size
    
    def getName(self):
        return self._name
    
    def getMaxADU(self):
        return self._max_adu 
       
    def isColorCam(self):
        return True
    
    def capture(self, isRecording, withFlat=False):
        if not self._picam2:
            return  
        
        array = self._picam2.capture_array('raw').view(np.uint16)

        # crop
        crop_x = 0
        if self._crop:
            array = array[self._crop_y:self._crop_y+self._crop_height,crop_x:crop_x+self._sensor_size[0]]
        else:
            array = array[self._preview_crop_y:self._preview_crop_y+self._preview_crop_height,crop_x:crop_x+self._sensor_size[0]] 

        offset = 3200
        bin = 2
        depth_conv = 4   

        if not isRecording:
            b = getMaxAduValue(array[:, 0::2][::2])
            g = getMaxAduValue(array[:, 0::2][1::2])
            r = getMaxAduValue(array[:, 1::2][1::2])
            self._max_adu = (r,g,b)
        
        if self._monobin:
            match self._monobin_mode:
                # rgb monobin
                case 0:
                    array_16bit = (bin2dBayer(np.array(array), bin) * depth_conv) - offset # convert 12-bit values to 16 bit
                # red layer
                case 1:
                    array_16bit = (array[:, 1::2][1::2] * depth_conv) - offset/4 # convert 12-bit values to 16 bit
                # green layer
                case 2:
                    array_16bit = (array[:, 0::2][1::2]+array[:, 1::2][::2] * depth_conv) - offset/4 # convert 12-bit values to 16 bit    
                # blue layer
                case 3:
                    array_16bit = (array[:, 0::2][::2] * depth_conv) - offset/4 # convert 12-bit values to 16 bit
  
            array_16bit[array_16bit>65535]=65535
            frame = np.uint16(array_16bit)
        else:
            f = cv2.cvtColor(array * 16 , cv2.COLOR_BayerRGGB2RGB)
            height = f.shape[0]//4
            width = f.shape[1]//4
            r = cv2.resize(f, (width, height))
            frame = np.uint16(r)
        return frame
           
    def stop(self):
        if not self._picam2:
            return
        self._picam2.stop()
        self._picam2.stop_encoder()
        self._picam2.close()

    def updateCameraControls(self, options):
        if not self._picam2:
            return
        
        restart = False

        if self._cameraControls and self._cameraControls.ExposureTime >= 1000000.0:
            self._picam2.stop()
            restart = True
        
        self._cameraControls = Controls(self._picam2)
        self._cameraControls.AeEnable = 0 if options['monobin'] else 1
        self._cameraControls.AwbEnable = False
        self._cameraControls.FrameDurationLimits = (int(150*1e3),60000000)
        self._cameraControls.ExposureTime = int(options['exposure_time'])
        self._cameraControls.AnalogueGain = 1.0 if not options['monobin'] else options['gain']
        self._cameraControls.Contrast = 0.0
        self._cameraControls.Brightness = 0.0
        self._cameraControls.NoiseReductionMode = controls.draft.NoiseReductionModeEnum.Off

        self._picam2.set_controls(self._cameraControls)

        if restart:
            self._picam2.start()
            time.sleep(1)

        self._crop = options['crop']
        self._crop_y = options['crop_y']
        
        self._preview_crop_y = options['preview_crop_y']
        self._preview_crop_height = options['preview_crop_height']

        self._monobin = options['monobin']
        self._monobin_mode = options['monobin_mode']
        self._bin = options['bin']

        
    



@jit(nopython=True)
def bin2dBayer(a,K):
    m_bins = a.shape[0]//K
    n_bins = a.shape[1]//K
    return a.reshape(m_bins, K, n_bins, K).sum(3).sum(1)

@jit(nopython=True)
def clip_and_cast(arr):
    arr = np.minimum(np.maximum(arr, 0), 65535)
    return arr.astype(np.uint16)




